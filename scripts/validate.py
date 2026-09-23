#!/usr/bin/env python3
"""
Validates books.json and all referenced book.json files against the
Book of Infinite Tales format specification.

Usage:
  python scripts/validate.py                          # validates books.json in current dir
  python scripts/validate.py <books.json>             # validates specified index
  python scripts/validate.py <book.json>              # validates a single book
  python scripts/validate.py --missing                # list every missing passage individually
  python scripts/validate.py --missing <book.json>    # same, for a specific book

Exit code 0 = valid (warnings may be printed).
Exit code 1 = one or more errors.
"""

import json
import re
import sys
from pathlib import Path

VALID_RETINUE = {"beside", "nearby", "absent"}
VALID_CATEGORIES = {"Martial", "Spiritual", "Courtly", "Wilderness"}
BUILTIN_SKILLS = {
    "Warfare", "Sword & Shield", "Mounted",
    "Piety", "Wisdom", "Magic",
    "Diplomacy", "Cunning", "Honor",
    "Nature Lore", "Endure Hardship", "Hunting",
}
QUEST_BODY = "Refer to physical Book of Tales for this passage."


def load_json(path, errors, label):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        errors.append(f"{label}: file not found: {path}")
    except json.JSONDecodeError as e:
        errors.append(f"{label}: invalid JSON — {e}")
    return None


def resolve_entries(book, book_dir, errors, label):
    raw = book.get("entries")
    if raw is None:
        errors.append(f"{label}: missing required field 'entries'")
        return []
    if isinstance(raw, str):
        entries_path = book_dir / raw
        data = load_json(entries_path, errors, f"{label}/entries({raw})")
        if data is None:
            return []
        raw = data
    if isinstance(raw, dict):
        raw = list(raw.values())
    if not isinstance(raw, list):
        errors.append(f"{label}: 'entries' must be an array, object map, or filename string")
        return []
    return raw


def load_components(book, book_dir, errors, label):
    comp_ref = book.get("components")
    if not comp_ref:
        return {}
    comp_path = book_dir / comp_ref
    data = load_json(comp_path, errors, f"{label}/components({comp_ref})")
    return data or {}


def get_using_valid_values(components):
    valid = set(VALID_CATEGORIES) | {"Any"}
    if components.get("skills"):
        valid |= {s["name"] for s in components["skills"]}
    else:
        valid |= BUILTIN_SKILLS
    if components.get("renown"):
        valid |= {r["name"] for r in components["renown"]}
    return valid


LINK = re.compile(r"\[\[([^\[\]|]+?)(?:\|[^\[\]]+?)?\]\]")


def is_formula(value):
    """{base} plus addLocationNumber and/or addAgeNumber set to true, as the reader accepts."""
    if not isinstance(value, dict) or not isinstance(value.get("base"), (int, float)):
        return False
    loc, age = value.get("addLocationNumber"), value.get("addAgeNumber")
    if loc not in (None, True) or age not in (None, True):
        return False
    return loc is True or age is True


def check_links(text, path, entry_ids, errors):
    for match in LINK.finditer(text or ""):
        target = match.group(1).strip()
        if target not in entry_ids:
            errors.append(f"{path}: link [[{target}]] points to an entry that does not exist")


def validate_target(target, path, errors):
    if isinstance(target, (int, float)):
        return
    if not is_formula(target):
        errors.append(
            f"{path}: target must be a number or {{base}} with addLocationNumber and/or addAgeNumber set to true"
        )


def validate_rewards(rewards, path, errors, valid_renown, valid_treasures, valid_statuses, valid_story_tokens):
    if not isinstance(rewards, dict):
        errors.append(f"{path}: rewards must be an object")
        return

    destiny = rewards.get("destiny")
    if (
        destiny is not None
        and not isinstance(destiny, (int, float))
        and destiny != "location_number"
        and not is_formula(destiny)
    ):
        errors.append(
            f"{path}: rewards.destiny must be a number, 'location_number', "
            f"or {{base}} with addLocationNumber and/or addAgeNumber"
        )

    notes = rewards.get("notes")
    if notes is not None and (
        not isinstance(notes, list) or any(not isinstance(n, str) or not n.strip() for n in notes)
    ):
        errors.append(f"{path}: rewards.notes must be a list of non-empty strings")

    renown = rewards.get("renown")
    if renown is not None:
        if not isinstance(renown, list):
            errors.append(f"{path}: rewards.renown must be an array")
        else:
            for i, r in enumerate(renown):
                if not isinstance(r, dict):
                    errors.append(f"{path}: rewards.renown[{i}] must be an object")
                    continue
                rtype = r.get("type")
                types = rtype if isinstance(rtype, list) else [rtype]
                if not types or not all(isinstance(t, str) for t in types):
                    errors.append(
                        f"{path}: rewards.renown[{i}].type must be a string or a non-empty list of strings"
                    )
                elif valid_renown:
                    for t in types:
                        if t not in valid_renown:
                            errors.append(
                                f"{path}: rewards.renown[{i}].type '{t}' is not a declared renown type"
                            )
                if not isinstance(r.get("delta"), (int, float)):
                    errors.append(f"{path}: rewards.renown[{i}].delta must be a number")

    skills = rewards.get("skills")
    if skills is not None:
        if not isinstance(skills, list):
            errors.append(f"{path}: rewards.skills must be an array")
        else:
            for i, s in enumerate(skills):
                if not isinstance(s, dict):
                    errors.append(f"{path}: rewards.skills[{i}] must be an object")
                    continue
                if "name" in s and not isinstance(s["name"], str):
                    errors.append(f"{path}: rewards.skills[{i}].name must be a string")
                if "category" in s and s["category"] not in VALID_CATEGORIES:
                    errors.append(
                        f"{path}: rewards.skills[{i}].category '{s['category']}' must be one of "
                        f"{sorted(VALID_CATEGORIES)}"
                    )
                if "count" in s and not isinstance(s["count"], int):
                    errors.append(f"{path}: rewards.skills[{i}].count must be an integer")

    treasures = rewards.get("treasures")
    if treasures is not None:
        if isinstance(treasures, str):
            if valid_treasures and treasures not in valid_treasures:
                errors.append(f"{path}: rewards.treasures '{treasures}' is not a declared treasure name")
        elif not isinstance(treasures, (int, float)):
            errors.append(f"{path}: rewards.treasures must be a number or string")

    statuses = rewards.get("statuses")
    if statuses is not None:
        if not isinstance(statuses, list):
            errors.append(f"{path}: rewards.statuses must be an array")
        else:
            for i, s in enumerate(statuses):
                if not isinstance(s, dict):
                    errors.append(f"{path}: rewards.statuses[{i}] must be an object")
                    continue
                if s.get("action") not in ("gain", "lose"):
                    errors.append(f"{path}: rewards.statuses[{i}].action must be 'gain' or 'lose'")
                sname = s.get("name")
                if not isinstance(sname, str):
                    errors.append(f"{path}: rewards.statuses[{i}].name must be a string")
                elif valid_statuses and sname not in valid_statuses:
                    errors.append(f"{path}: rewards.statuses[{i}].name '{sname}' is not a declared status name")

    story_token = rewards.get("storyToken")
    if story_token is not None:
        if not isinstance(story_token, int):
            errors.append(f"{path}: rewards.storyToken must be an integer")
        elif valid_story_tokens and story_token not in valid_story_tokens:
            errors.append(f"{path}: rewards.storyToken {story_token} is not a declared story token number")

    movement = rewards.get("movement")
    if movement is not None and not isinstance(movement, (int, float)) and movement != "free":
        errors.append(f"{path}: rewards.movement must be a number or 'free'")


def enumerate_required_passages(components):
    """Return dict of passage_id -> (description, category) for all required passages."""
    passages = {}

    def add(pid, desc, category):
        passages[str(pid)] = (desc, category)

    for age in components.get("ages", []):
        if age.get("startPassage"):
            add(age["startPassage"], f"Age start — {age['name']}", "Age start")

    for character in components.get("characters", []):
        for feature in components.get("features", []):
            add(
                character["base"] + feature["offset"],
                f"{feature['name']} {character['name']}",
                "Character encounter",
            )

    for location in components.get("locations", []):
        add(location["passage"], f"Location — {location['name']}", "Location card draw")
        for age in components.get("ages", []):
            visit_id = location.get("visitPassages", {}).get(age["id"])
            if visit_id:
                add(
                    visit_id,
                    f"Place of Power — {location['name']} ({age['name']})",
                    "Place of Power",
                )

    for age in components.get("ages", []):
        milieu_base = age.get("milieuBase")
        if milieu_base is not None:
            for milieu in components.get("milieus", []):
                for terrain in components.get("terrains", []):
                    offset = milieu.get("terrainOffsets", {}).get(terrain["id"])
                    if offset is not None:
                        add(
                            milieu_base + offset,
                            f"Milieu — {milieu['name']} × {terrain['name']}",
                            "Milieu encounter",
                        )

    for quest in components.get("quests", []):
        add(quest["passage"], f"Quest — {quest['name']}", "Quest")

    for status in components.get("statuses", []):
        for enc in status.get("encounters", []):
            add(enc["passage"], f"Status — {status['name']}: {enc['label']}", "Status encounter")

    if components.get("epiloguePassage"):
        add(components["epiloguePassage"], "Epilogue", "Epilogue")

    return passages


def validate_book(book_json_path, show_missing=False):
    errors = []
    warnings = []
    label = str(book_json_path)
    book_dir = book_json_path.parent

    book = load_json(book_json_path, errors, label)
    if book is None:
        return errors, warnings

    if book.get("schema") != "book-of-infinite-tales/v1":
        errors.append(
            f"{label}: schema must be 'book-of-infinite-tales/v1', got {book.get('schema')!r}"
        )

    if not isinstance(book.get("title"), str):
        errors.append(f"{label}: missing required string field 'title'")

    components = load_components(book, book_dir, errors, label)

    valid_using = get_using_valid_values(components)
    valid_renown = {r["name"] for r in components.get("renown", [])} | {"Any"} if components.get("renown") else set()
    valid_treasures = {t["name"] for t in components.get("treasures", [])} if components.get("treasures") else set()
    valid_statuses = {s["name"] for s in components.get("statuses", [])} if components.get("statuses") else set()
    valid_story_tokens = {t["number"] for t in components.get("storyTokens", [])} if components.get("storyTokens") else set()

    # Passage ids from components that must use the restricted body text
    restricted_passages = {}
    for quest in components.get("quests", []):
        restricted_passages[str(quest["passage"])] = f"Quest — {quest['name']}"
    for status in components.get("statuses", []):
        for enc in status.get("encounters", []):
            restricted_passages[str(enc["passage"])] = f"Status — {status['name']}: {enc['label']}"

    raw_entries = resolve_entries(book, book_dir, errors, label)

    # Build entry map, checking for duplicates
    entries_by_id = {}
    for i, entry in enumerate(raw_entries):
        if not isinstance(entry, dict):
            errors.append(f"{label}: entries[{i}] must be an object")
            continue
        eid = entry.get("id")
        if not isinstance(eid, str):
            errors.append(f"{label}: entries[{i}].id must be a string")
            continue
        if eid in entries_by_id:
            errors.append(f"{label}: duplicate entry id '{eid}'")
        entries_by_id[eid] = entry

    entry_ids = set(entries_by_id)

    for eid, entry in entries_by_id.items():
        path = f"{label}#{eid}"

        if not isinstance(entry.get("body"), str):
            errors.append(f"{path}: missing required string field 'body'")
        else:
            check_links(entry["body"], path, entry_ids, errors)
        for note in (entry.get("rewards") or {}).get("notes") or [] if isinstance(entry.get("rewards"), dict) else []:
            if isinstance(note, str):
                check_links(note, f"{path}.rewards.notes", entry_ids, errors)

        # Quest and status passages must use the restricted body
        if eid in restricted_passages:
            if entry.get("body") != QUEST_BODY:
                errors.append(
                    f"{path}: {restricted_passages[eid]} body must be exactly "
                    f"{QUEST_BODY!r}"
                )
            for extra in ("responses", "resolutions", "rewards", "goto"):
                if entry.get(extra) is not None:
                    errors.append(
                        f"{path}: {restricted_passages[eid]} must not have '{extra}'"
                    )

        retinue = entry.get("retinue")
        if retinue is not None and retinue not in VALID_RETINUE:
            errors.append(
                f"{path}: retinue must be one of {sorted(VALID_RETINUE)}, got {retinue!r}"
            )

        romantic = entry.get("romantic")
        if romantic is not None and not isinstance(romantic, bool):
            errors.append(f"{path}: romantic must be a boolean")

        goto = entry.get("goto")
        if goto is not None:
            if not isinstance(goto, str):
                errors.append(f"{path}: goto must be a string")
            elif goto not in entry_ids:
                errors.append(f"{path}: goto '{goto}' does not exist")

        responses = entry.get("responses")
        if responses is not None:
            if not isinstance(responses, list):
                errors.append(f"{path}: responses must be an array")
            else:
                for j, opt in enumerate(responses):
                    rpath = f"{path}.responses[{j}]"
                    if not isinstance(opt, dict):
                        errors.append(f"{rpath}: must be an object")
                        continue
                    if not isinstance(opt.get("label"), str):
                        errors.append(f"{rpath}: missing required string field 'label'")
                    opt_goto = opt.get("goto")
                    if not isinstance(opt_goto, str):
                        errors.append(f"{rpath}: missing required string field 'goto'")
                    elif opt_goto not in entry_ids:
                        errors.append(f"{rpath}: goto '{opt_goto}' does not exist")
                    if opt.get("romantic") is not None and not isinstance(opt["romantic"], bool):
                        errors.append(f"{rpath}: romantic must be a boolean")

        resolutions = entry.get("resolutions")
        if resolutions is not None:
            if not isinstance(resolutions, list):
                errors.append(f"{path}: resolutions must be an array")
            else:
                for j, opt in enumerate(resolutions):
                    rpath = f"{path}.resolutions[{j}]"
                    if not isinstance(opt, dict):
                        errors.append(f"{rpath}: must be an object")
                        continue

                    using = opt.get("using")
                    if not isinstance(using, list) or not using:
                        errors.append(f"{rpath}: 'using' must be a non-empty array")
                    else:
                        for u in using:
                            if u not in valid_using:
                                errors.append(
                                    f"{rpath}: 'using' value '{u}' is not a valid skill, "
                                    f"category, or renown type"
                                )
                        if opt.get("total") is True and not all(u in VALID_CATEGORIES for u in using):
                            errors.append(f"{rpath}: \"total\": true needs skill categories in 'using'")

                    if "target" not in opt:
                        errors.append(f"{rpath}: missing required field 'target'")
                    else:
                        validate_target(opt["target"], rpath, errors)

                    partial = opt.get("partial")
                    if partial is not None:
                        if not isinstance(partial, dict) or not isinstance(partial.get("min"), (int, float)):
                            errors.append(f"{rpath}.partial: needs a numeric 'min'")
                        elif isinstance(opt.get("target"), (int, float)) and partial["min"] >= opt["target"]:
                            errors.append(f"{rpath}.partial: 'min' must be below the target")

                    for outcome_key in ("success", "partial", "failure"):
                        outcome = opt.get(outcome_key)
                        if outcome_key == "partial" and outcome is None:
                            continue
                        if not isinstance(outcome, dict):
                            errors.append(f"{rpath}: missing required object field '{outcome_key}'")
                            continue
                        if not isinstance(outcome.get("body"), str):
                            errors.append(f"{rpath}.{outcome_key}: missing required string field 'body'")
                        else:
                            check_links(outcome["body"], f"{rpath}.{outcome_key}", entry_ids, errors)
                        for note in (outcome.get("rewards") or {}).get("notes") or []:
                            if isinstance(note, str):
                                check_links(note, f"{rpath}.{outcome_key}.notes", entry_ids, errors)
                        out_goto = outcome.get("goto")
                        if out_goto is not None:
                            if not isinstance(out_goto, str):
                                errors.append(f"{rpath}.{outcome_key}: goto must be a string")
                            elif out_goto not in entry_ids:
                                errors.append(
                                    f"{rpath}.{outcome_key}: goto '{out_goto}' does not exist"
                                )
                        if outcome.get("rewards") is not None:
                            validate_rewards(
                                outcome["rewards"],
                                f"{rpath}.{outcome_key}",
                                errors,
                                valid_renown,
                                valid_treasures,
                                valid_statuses,
                                valid_story_tokens,
                            )

                    if opt.get("romantic") is not None and not isinstance(opt["romantic"], bool):
                        errors.append(f"{rpath}: romantic must be a boolean")

        if entry.get("rewards") is not None:
            validate_rewards(
                entry["rewards"],
                path,
                errors,
                valid_renown,
                valid_treasures,
                valid_statuses,
                valid_story_tokens,
            )

    # Warn about required passages not yet present
    if components:
        required = enumerate_required_passages(components)
        missing = {
            pid: (desc, category)
            for pid, (desc, category) in required.items()
            if pid not in entry_ids
        }
        if missing and show_missing:
            for pid, (desc, _) in sorted(
                missing.items(), key=lambda kv: (int(kv[0]) if kv[0].isdigit() else kv[0])
            ):
                warnings.append(f"{label}: missing passage {pid} — {desc}")
        else:
            missing_by_category = {}
            for pid, (desc, category) in missing.items():
                missing_by_category.setdefault(category, []).append(pid)
            for category, pids in sorted(missing_by_category.items()):
                example = sorted(pids, key=lambda p: int(p) if p.isdigit() else p)[0]
                warnings.append(
                    f"{label}: {len(pids)} missing {category} passage(s) (e.g. {example})"
                )

    return errors, warnings


def validate_index(index_path, show_missing=False):
    errors = []
    warnings = []
    label = str(index_path)
    index_dir = index_path.parent

    data = load_json(index_path, errors, label)
    if data is None:
        return errors, warnings

    if data.get("schema") != "book-of-infinite-tales/index/v1":
        errors.append(
            f"{label}: schema must be 'book-of-infinite-tales/index/v1', "
            f"got {data.get('schema')!r}"
        )

    if not isinstance(data.get("title"), str):
        errors.append(f"{label}: missing required string field 'title'")

    books = data.get("books")
    if not isinstance(books, list):
        errors.append(f"{label}: missing required array field 'books'")
        return errors, warnings

    for i, book_entry in enumerate(books):
        if not isinstance(book_entry, dict):
            errors.append(f"{label}: books[{i}] must be an object")
            continue
        if not isinstance(book_entry.get("path"), str):
            errors.append(f"{label}: books[{i}].path must be a string")
            continue
        if not isinstance(book_entry.get("title"), str):
            errors.append(f"{label}: books[{i}].title must be a string")

        book_json = index_dir / book_entry["path"] / "book.json"
        berrs, bwarns = validate_book(book_json, show_missing=show_missing)
        errors.extend(berrs)
        warnings.extend(bwarns)

    return errors, warnings


def main():
    flags = {a for a in sys.argv[1:] if a.startswith("-")}
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    show_missing = "--missing" in flags
    target = Path(args[0]) if args else Path("books.json")

    if not target.exists():
        print(f"error: {target} not found", file=sys.stderr)
        sys.exit(1)

    if target.name == "book.json":
        errors, warnings = validate_book(target, show_missing=show_missing)
    else:
        errors, warnings = validate_index(target, show_missing=show_missing)

    for w in warnings:
        print(f"warning: {w}")

    for e in errors:
        print(f"error: {e}")

    if errors:
        print(f"\n{len(errors)} error(s).", file=sys.stderr)
        sys.exit(1)

    if warnings:
        print(f"\n{len(warnings)} warning(s) — book is valid.")
    else:
        print("All valid.")


if __name__ == "__main__":
    main()

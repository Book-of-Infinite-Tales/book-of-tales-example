#!/usr/bin/env python3
"""Compile the .tales source files in this directory into ../book.json.

Usage (from the repo root):
    python3 la-morte-d-arthur/source/build.py [OUTPUT] [COMPONENTS]

OUTPUT defaults to la-morte-d-arthur/book.json and COMPONENTS to the repo's
tales-of-the-arthurian-knights-components.json. Symbolic ids are given free
passage numbers from a fixed shuffle, so rebuilding unchanged sources gives an
identical book.json. idmap.json (symbolic id -> passage number) is written
alongside the sources.

Source format (one entry per block):

=== 1001            numeric id (formula passage) or a symbolic id like k01a
Body paragraphs. Blank line = paragraph break.
[d:2 | sk:Courtly | rn:Villainy+1]      entry rewards (before any ??)
> You may help the king. -> k01a        response (label starting "* " is romantic)
=> k01b                                 entry goto (before any ??) / outcome goto (inside)
?? label | Cunning | 4                  check option (??* romantic). using "A/B"; target 4, 3+L, 5+A; 4th field "total"
++ success text...
[rewards]
~~2 partial text...                     partial band with min
[rewards]
-- failure text...
[rewards]

Rewards: d:2 d:L d:1+L d:A  sk:Name sk:Category sk:Martial*2  rn:Divinity/Romance+2 rn:Any+1 rn:Divinity-1
         st:+Blessed st:-Unhorsed  tr:1 tr:Holy Lance  tok:12  mv:1 mv:free  n:free note
"""
import json, random, re, sys, glob, os

HERE = os.path.dirname(os.path.abspath(__file__))
COMP = json.load(open(sys.argv[2] if len(sys.argv) > 2 else
                      os.path.join(HERE, "..", "..", "tales-of-the-arthurian-knights-components.json")))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "book.json")

SKILLS = {s["name"] for s in COMP["skills"]}
CATS = {"Martial", "Spiritual", "Courtly", "Wilderness"}
RENOWN = {"Divinity", "Romance", "Villainy", "Any"}
STATUSES = {s["name"] for s in COMP["statuses"]}
TREASURES = {t["name"] for t in COMP["treasures"]}
TOKENS = {t["number"] for t in COMP["storyTokens"]}
PHYSICAL = "Refer to physical Book of Tales for this passage."

errors = []


def reserved_ids():
    r = set()
    for a in COMP["ages"]:
        r.add(int(a["startPassage"]))
    for c in COMP["characters"]:
        for f in COMP["features"]:
            r.add(c["base"] + f["offset"])
    for a in COMP["ages"]:
        for m in COMP["milieus"]:
            for off in m["terrainOffsets"].values():
                r.add(a["milieuBase"] + off)
    for l in COMP["locations"]:
        r.add(int(l["passage"]))
        for v in l["visitPassages"].values():
            r.add(int(v))
    for q in COMP["quests"]:
        r.add(int(q["passage"]))
    for s in COMP["statuses"]:
        for e in s.get("encounters", []):
            r.add(int(e["passage"]))
    r.add(int(COMP["epiloguePassage"]))
    return r


def formula(s, where):
    s = s.strip()
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if s == "L":
        return "location_number"
    m = re.fullmatch(r"(\d+)?((?:\+?[LA])+)", s.replace(" ", ""))
    if not m:
        errors.append(f"{where}: bad formula {s!r}")
        return 0
    f = {"base": int(m.group(1) or 0)}
    if "L" in m.group(2):
        f["addLocationNumber"] = True
    if "A" in m.group(2):
        f["addAgeNumber"] = True
    return f


def parse_rewards(text, where):
    r = {}
    for item in [i.strip() for i in text.split(" | ") if i.strip()]:
        if ":" not in item:
            errors.append(f"{where}: bad reward item {item!r}")
            continue
        k, v = item.split(":", 1)
        k, v = k.strip(), v.strip()
        if k == "d":
            r["destiny"] = formula(v, where)
        elif k == "sk":
            cnt = 1
            if "*" in v:
                v, c = v.split("*")
                v, cnt = v.strip(), int(c)
            if v in SKILLS:
                s = {"name": v}
            elif v in CATS:
                s = {"category": v}
            else:
                errors.append(f"{where}: unknown skill {v!r}")
                continue
            if cnt != 1:
                s["count"] = cnt
            r.setdefault("skills", []).append(s)
        elif k == "rn":
            m = re.fullmatch(r"([A-Za-z/]+)([+-]\d+)", v.replace(" ", ""))
            if not m:
                errors.append(f"{where}: bad renown {v!r}")
                continue
            types = m.group(1).split("/")
            for t in types:
                if t not in RENOWN:
                    errors.append(f"{where}: unknown renown {t!r}")
            r.setdefault("renown", []).append({"type": types if len(types) > 1 else types[0], "delta": int(m.group(2))})
        elif k == "st":
            act = {"+": "gain", "-": "lose"}.get(v[0])
            name = v[1:].strip()
            if not act or name not in STATUSES:
                errors.append(f"{where}: bad status {v!r}")
                continue
            r.setdefault("statuses", []).append({"action": act, "name": name})
        elif k == "tr":
            if re.fullmatch(r"\d+", v):
                r["treasures"] = int(v)
            elif v in TREASURES:
                r["treasures"] = v
            else:
                errors.append(f"{where}: unknown treasure {v!r}")
        elif k == "tok":
            if int(v) not in TOKENS:
                errors.append(f"{where}: unknown token {v}")
            r["storyToken"] = int(v)
        elif k == "mv":
            r["movement"] = "free" if v == "free" else int(v)
        elif k == "n":
            r.setdefault("notes", []).append(v)
        else:
            errors.append(f"{where}: unknown reward key {k!r}")
    return r


def paragraphs(lines):
    paras, cur = [], []
    for ln in lines:
        if ln.strip():
            cur.append(ln.strip())
        elif cur:
            paras.append(" ".join(cur))
            cur = []
    if cur:
        paras.append(" ".join(cur))
    return "\n\n".join(paras)


def parse_entry(eid, lines, src):
    where = f"{src}:{eid}"
    e = {"id": eid}
    body, opts = [], []
    cur_opt, cur_side, side_lines = None, None, []

    def close_side():
        nonlocal side_lines
        if cur_opt is not None and cur_side is not None:
            cur_opt[cur_side]["body"] = paragraphs(side_lines)
        side_lines = []

    for ln in lines:
        s = ln.strip()
        if s.startswith("?? ") or s.startswith("??* "):
            close_side()
            romantic = s.startswith("??*")
            parts = [p.strip() for p in s[3 if not romantic else 4:].split("|")]
            if len(parts) < 3:
                errors.append(f"{where}: bad option header {s!r}")
                continue
            using = parts[1].split("/")
            for u in using:
                if u not in SKILLS | CATS | RENOWN:
                    errors.append(f"{where}: unknown using {u!r}")
            cur_opt = {"label": parts[0], "using": using, "target": formula(parts[2], where)}
            if len(parts) > 3 and parts[3] == "total":
                cur_opt["total"] = True
            if romantic:
                cur_opt["romantic"] = True
            opts.append(cur_opt)
            cur_side = None
        elif s.startswith("++") and cur_opt is not None:
            close_side()
            cur_side = "success"
            cur_opt["success"] = {}
            side_lines = [s[2:]]
        elif s.startswith("~~") and cur_opt is not None:
            close_side()
            cur_side = "partial"
            m = re.match(r"~~\s*(\d+)\s*(.*)", s)
            cur_opt["partial"] = {"min": int(m.group(1))}
            side_lines = [m.group(2)]
        elif s.startswith("--") and cur_opt is not None:
            close_side()
            cur_side = "failure"
            cur_opt["failure"] = {}
            side_lines = [s[2:]]
        elif s.startswith("[") and s.endswith("]") and not s.startswith("[["):
            rw = parse_rewards(s[1:-1], where)
            if cur_opt is not None and cur_side is not None:
                cur_opt[cur_side]["rewards"] = rw
            else:
                e["rewards"] = rw
        elif s.startswith("=> "):
            tgt = s[3:].strip()
            if cur_opt is not None and cur_side is not None:
                cur_opt[cur_side]["goto"] = tgt
            else:
                e["goto"] = tgt
        elif s.startswith("> "):
            m = re.match(r">\s*(.+?)\s*->\s*(\S+)\s*$", s)
            if not m:
                errors.append(f"{where}: bad response {s!r}")
                continue
            resp = {"label": m.group(1), "goto": m.group(2)}
            if resp["label"].startswith("* "):
                resp["romantic"] = True
            e.setdefault("responses", []).append(resp)
        else:
            if cur_opt is not None and cur_side is not None:
                side_lines.append(ln)
            elif cur_opt is None:
                body.append(ln)
            elif s:
                errors.append(f"{where}: stray text inside option before ++: {s[:40]!r}")
    close_side()
    e["body"] = paragraphs(body)
    if opts:
        for o in opts:
            for side in ("success", "failure"):
                if side not in o:
                    errors.append(f"{where}: option {o['label']!r} missing {side}")
        # order keys nicely
        e["resolutions"] = [{k: o[k] for k in ("label", "using", "total", "target", "romantic", "success", "partial", "failure") if k in o}
                            for o in opts]
    order = ["id", "body", "romantic", "rewards", "responses", "resolutions", "goto"]
    return {k: e[k] for k in order if k in e}


def main():
    files = sorted(glob.glob(os.path.join(HERE, "*.tales")))
    entries, order = {}, []
    for fpath in files:
        src = os.path.basename(fpath)
        text = open(fpath, encoding="utf-8").read()
        blocks = re.split(r"^=== *(\S+) *$", text, flags=re.M)
        for i in range(1, len(blocks), 2):
            eid, content = blocks[i], blocks[i + 1]
            if eid in entries:
                errors.append(f"{src}: duplicate id {eid}")
                continue
            entries[eid] = parse_entry(eid, content.split("\n"), src)
            order.append(eid)

    # physical passages
    for q in COMP["quests"]:
        entries.setdefault(q["passage"], {"id": q["passage"], "body": PHYSICAL}); order.append(q["passage"])
    for s in COMP["statuses"]:
        for enc in s.get("encounters", []):
            entries.setdefault(enc["passage"], {"id": enc["passage"], "body": PHYSICAL}); order.append(enc["passage"])

    # referrers
    LINK = re.compile(r"\[\[([^\[\]|]+?)(\|[^\[\]]+?)?\]\]")
    refs = {}

    def texts(e):
        yield e.get("body", "")
        for n in (e.get("rewards") or {}).get("notes", []):
            yield n
        for o in e.get("resolutions", []):
            for side in ("success", "partial", "failure"):
                if side in o:
                    yield o[side].get("body", "")
                    for n in (o[side].get("rewards") or {}).get("notes", []):
                        yield n

    def targets(e):
        for r in e.get("responses", []):
            yield r["goto"]
        if "goto" in e:
            yield e["goto"]
        for o in e.get("resolutions", []):
            for side in ("success", "partial", "failure"):
                if side in o and "goto" in o[side]:
                    yield o[side]["goto"]
        for t in texts(e):
            for m in LINK.finditer(t):
                yield m.group(1).strip()

    for eid in order:
        for t in targets(entries[eid]):
            refs.setdefault(t, []).append(eid)

    # assign numeric ids to symbolic ones
    reserved = reserved_ids()
    explicit = {int(k) for k in entries if k.isdigit()}
    pool = [n for n in range(1001, 3000) if n not in reserved and n not in explicit and n not in (1054, 2134)]
    random.Random(1485).shuffle(pool)
    mapping = {}
    for eid in order:
        if eid.isdigit():
            continue
        parents = [mapping.get(p, p) for p in refs.get(eid, [])]
        pnums = [int(p) for p in parents if str(p).isdigit()]
        for idx, n in enumerate(pool):
            if all(abs(n - p) > 15 for p in pnums):
                mapping[eid] = str(n)
                pool.pop(idx)
                break
        else:
            errors.append(f"out of ids for {eid}")

    def fix(t):
        return LINK.sub(lambda m: "[[" + mapping.get(m.group(1).strip(), m.group(1).strip()) + (m.group(2) or "") + "]]", t)

    out = []
    for eid in order:
        e = json.loads(json.dumps(entries[eid]))
        e["id"] = mapping.get(eid, eid)
        e["body"] = fix(e["body"])
        for r in e.get("responses", []):
            if r["goto"] not in entries:
                errors.append(f"{eid}: response goto {r['goto']} missing")
            r["goto"] = mapping.get(r["goto"], r["goto"])
        if "goto" in e:
            if e["goto"] not in entries:
                errors.append(f"{eid}: goto {e['goto']} missing")
            e["goto"] = mapping.get(e["goto"], e["goto"])
        if "rewards" in e and "notes" in e["rewards"]:
            e["rewards"]["notes"] = [fix(n) for n in e["rewards"]["notes"]]
        for o in e.get("resolutions", []):
            for side in ("success", "partial", "failure"):
                if side in o:
                    o[side]["body"] = fix(o[side]["body"])
                    if "goto" in o[side]:
                        if o[side]["goto"] not in entries:
                            errors.append(f"{eid}: outcome goto {o[side]['goto']} missing")
                        o[side]["goto"] = mapping.get(o[side]["goto"], o[side]["goto"])
                    rw = o[side].get("rewards")
                    if rw and "notes" in rw:
                        rw["notes"] = [fix(n) for n in rw["notes"]]
        for t in texts(entries[eid]):
            for m in LINK.finditer(t):
                if m.group(1).strip() not in entries:
                    errors.append(f"{eid}: link [[{m.group(1)}]] missing")
        out.append(e)

    # unreachable symbolic entries
    for eid in order:
        if not eid.isdigit() and eid not in refs:
            errors.append(f"{eid}: symbolic entry is never referenced")

    out.sort(key=lambda e: int(e["id"]))
    book = {
        "schema": "book-of-infinite-tales/v1",
        "title": "La Morte D'Arthur",
        "author": "Rob McArthur",
        "version": "2.0.0",
        "description": "Arthur's Britain from the young king's crowning through the Grail's terrible light to the last battle on Salisbury Plain, told in encounters inspired by Sir Thomas Malory.",
        "components": "../tales-of-the-arthurian-knights-components.json",
        "aiGenerated": True,
        "entries": out,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(book, f, indent=2, ensure_ascii=False)
        f.write("\n")
    json.dump(mapping, open(os.path.join(HERE, "idmap.json"), "w"), indent=1)
    missing = sorted(reserved - {int(e["id"]) for e in out})
    print(f"{len(out)} entries written to {OUT}; {len(missing)} required passages still missing")
    for e_ in errors:
        print("ERROR", e_)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()

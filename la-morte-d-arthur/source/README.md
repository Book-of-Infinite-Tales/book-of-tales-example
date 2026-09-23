# La Morte D'Arthur: source

`../book.json` is built from the `.tales` files in this folder. Edit the sources, then rebuild from the repo root:

```bash
python3 la-morte-d-arthur/source/build.py
```

Rebuilding unchanged sources produces an identical `book.json`. After a rebuild, check the result:

```bash
python3 scripts/validate.py
```

## Files

| Files | Contents |
|---|---|
| `00-ages.tales` | Age starts (1000, 2000, 3000) and the epilogue (9999) |
| `01`–`12` | Character encounters, one file per character card |
| `20`–`28` | Milieu encounters, one file per milieu, all six terrains and three ages |
| `30`–`32` | Places of Power and location card draws |
| `build.py` | Compiler; its docstring documents the `.tales` format |
| `idmap.json` | Written by the build: symbolic id → passage number |

## The format in brief

Each passage starts with `=== ID`. Formula passages use their real number (`=== 1001`). Every resolution and result passage uses a symbolic id (`=== k01a`), and the build gives it a free passage number from a fixed shuffle, far from the passage that leads to it. Write links as `[[k01a]]` and gotos as `-> k01a`. The build turns them into the real numbers.

```
=== 1001
Response text, with dialogue.
> You may help the king. -> k01a
> * You may court the miller's daughter. -> k01b

=== k01a
Lead-in.
?? keep the peace | Diplomacy | 4
++ Success text.
[d:2 | sk:Courtly | rn:Romance+1]
-- Failure text.
[sk:Diplomacy | st:+Scorned]
```

Targets can be a number, or `3+L` (plus the Location #) or `5+A` (plus the Age #). Add a fourth field, `total`, for a category-total check. Mark a partial band with `~~2`. Reward keys: `d` destiny, `sk` skill, `rn` renown, `st` status, `tr` treasure, `tok` story token, `mv` movement, `n` note.

Symbolic ids are assigned in file order. Adding passages at the end of the last file keeps existing numbers stable. Inserting passages earlier renumbers every symbolic passage after them, which is harmless unless someone has noted a number from an earlier build.

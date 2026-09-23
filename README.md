# Book of Tales Examples

These are example Books of Tales compatible with the [Book of Infinite Tales](https://book-of-infinite-tales.github.io) reader for use with the board game *Tales of the Arthurian Knights*.

To load these examples, open the reader and enter:

```
RobMcA/book-of-tales-example
```

---

## What's in this collection

### La Morte d'Arthur

An AI-generated Book of Tales inspired by Sir Thomas Malory's *Le Morte d'Arthur*, written with the `book-of-tales-author` skill from the [Book of Tales Template](https://github.com/RobMcA/Book-of-Tales-Template). It covers all three game ages:

- **Golden Age of Camelot**: a beardless young king, eleven rebel kings under Lot of Orkney, Merlin at court, and the Round Table newly arrived from Cameliard.
- **Quest of the Holy Grail**: the veiled vessel passes through the hall at Pentecost, the fellowship scatters, and the land around Corbenic turns to dust.
- **Final Wars of Britain**: the queen at the stake, the siege of Benwick, Mordred crowned at Canterbury, and the last battle on Salisbury Plain.

The book has about 1,100 passages. It has every passage the components file calls for: the three age starts, all 132 character encounters, all 162 milieu encounters, the 12 location cards and their 36 Places of Power, and an epilogue scored by the table's renown. Quest and status-card passages refer players to the physical Book of Tales. Thirteen story-token threads carry consequences between encounters. For example, a knight who rode with King Lot is remembered at Camelot and in Orkney, and a knight who once befriended Mordred is recognised on Salisbury Plain.

The book uses the full reader schema: formula targets and Destiny, graded renown checks, category totals, "Divinity or Romance" rewards, and passage links for story-token gates. `scripts/validate.py` has been updated to accept these, to match the reader's own validation.

### The `aiGenerated` flag

`La Morte d'Arthur` sets `"aiGenerated": true` in its `book.json`. The reader app surfaces this flag to players so they know the prose was written by an AI model rather than hand-authored.

### `tales-of-the-arthurian-knights-components.json`

This file at the repo root defines all the game components shared across books in this collection: the three ages, six terrains, encounter features, twelve character types, nine milieus, twelve named locations, twenty-four quests, eighteen treasures, renown types, twelve skills, thirty story tokens, and all statuses. Each `book.json` references it via its `components` field so the definitions live in one place rather than being duplicated per book.

---

## Creating your own books

To create your own collection, fork the [Book of Tales Template](https://github.com/Book-of-Infinite-Tales/Book-of-Tales-Template). It contains:

- A complete [format reference](https://github.com/RobMcA/Book-of-Tales-Template/blob/main/docs/book_format.md) covering every field in `book.json` and `components.json`
- Helper scripts and an example book to get you started

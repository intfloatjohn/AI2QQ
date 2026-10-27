# Tools & Action Tags Specification (English)

The framework supports inline action tags in AI replies, which are automatically parsed and converted into rich QQ components by the daemon:

---

## 1. Native QQ Faces
- `[Send Face: Hug]` (ID 222)
- `[Send Face: Cuddle]` (ID 219)
- `[Send Face: Kiss]` (ID 109)
- `[Send Face: Shy]` (ID 6)
- `[Send Face: Pout]` (ID 106)
- `[Send Face: Smile]` (ID 14)
- `[Send Face: Cat]` (ID 307)
- `[Send Face: Heart]` (ID 319)

---

## 2. Custom Stickers
- `[Send Sticker: keyword]` (matches image files in `stickers/`, e.g. `heart.jpg`, `wave.jpg`, `sleep.jpg`)

---

## 3. Voice Messages (Edge-TTS)
- `[Send Voice: text to say]` (synthesizes audio on the fly and dispatches as a native QQ voice bubble)

---

## 4. Interactive Actions
- `[Interact: Poke]` (nudges/pokes user in QQ)
- `[Interact: Like]` (gives 10 thumbs-up likes to the user's profile card)

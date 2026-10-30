# Stickers Folder Guide

This folder holds your own stickers, memes and photos that the companion can send on its own.

[简体中文](STICKERS_GUIDE.md)

---

## 1. Adding a sticker
1. Put a `.jpg`, `.png` or `.gif` file in this folder.
2. Give it a short, memorable file name. The name is what the bot matches on:
   - `heart.jpg` (heart / love)
   - `wave.jpg` (hello / goodbye)
   - `sleep.jpg` (good night)
   - `pout.jpg` (sulking / annoyed)
   - `avatar.jpg` (selfie)

No restart is needed: the folder is read every time a sticker is sent.

---

## 2. How the bot finds and sends it
When the model writes `[sticker: keyword]` in a reply, the bot:
1. Looks for a file whose name contains the keyword (or the other way round), ignoring case.
2. If none matches, tries built-in aliases (for example "love" also finds `heart`).
3. Sends the matching image to the chat. The tag itself is removed from the text.

Stickers in this folder are also added to the picture library automatically, so `[PICTURE: keyword]` and the `search_picture_library` tool can find them too. In group chats they count as public pictures.

---

## 3. Letting the model know about new stickers
List your stickers in the persona prompt so the model knows they exist. In `persona/system_prompt_en.md`, extend the line that starts with "Custom Stickers", for example:

```
- Custom Stickers: `[sticker: heart]`, `[sticker: wave]`, `[sticker: sleep]`, `[sticker: your-new-sticker]`
```

The model will then pick a fitting sticker when it wants to.

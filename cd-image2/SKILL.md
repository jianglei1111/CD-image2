---
name: "cd-image2"
description: "Generate or edit images through the fixed CD-image2 channel at https://sp.chedankj.com/v1 using a user-provided image-group key. Use when the user wants image generation, image editing, logo/art/design assets, or asks to use image2/chedankj image generation."
---

# CD-image2

Use this skill for image generation or image editing through the bundled `scripts/image2_cli.py` client. The API base URL is fixed in the script as `https://sp.chedankj.com/v1`.

The bundled client intentionally uses `httpx` to match the known-working legacy image2 script. If `httpx` is missing, install it in the Python environment you will use to run the script:

```powershell
python -m pip install httpx
```

## Key Rule

Before calling the script, check the current conversation for a user-provided key for the `image` group. If there is no such key, stop and ask the user to create one at `https://www.chedankj.com` with group `image`, then send it in the chat.

Do not store the key in files or skill instructions. Pass it only for the current command through an environment variable:

```powershell
$env:IMAGE2_API_KEY="sk-..."
```

If the request fails and the error suggests authentication, authorization, unavailable accounts, or another key/channel issue, tell the user the HTTP status and the returned message. Briefly say the key or image group may be wrong when the error is consistent with that.

## Workflow

1. Understand the user's image goal before calling the script.
2. If the user gives a rough idea, improve it into a clear production prompt with composition, style, constraints, and avoid-list. If the user explicitly says the prompt is exact or must not be changed, use it directly.
3. Choose generation or editing:
   - Use `generate` for text-to-image.
   - Use `edit` only when there is a local image path to edit. If the user wants an edit but no usable image path is available, ask for the image or path first.
4. Choose practical parameters from the request:
   - Use `2048x2048` for 2K square output.
   - Use `1024x1024` when the user does not need high resolution.
   - Use `high` for final assets, logos, posters, and polished work.
   - Use `low` or `medium` only for quick tests or drafts.
5. For 4K or custom-size requests, apply the size rules below before calling the script. If the requested size is invalid, stop and explain the rule instead of sending the request.
6. Output into the current working directory. Let the script create a filename from a short slug plus timestamp, or pass a clear `--slug`.
7. Before running the command, tell the user generation has started and may be slow.
8. For `generate` requests, set the request timeout to `600` seconds (`--timeout 600`). Do not use a shorter request timeout for final 2K or 4K generations, and do not exceed 600 seconds unless the user explicitly asks.
9. Run with a command timeout of at least 11 minutes so the 600-second request timeout can complete cleanly. Do not report success until the command has returned and the output file exists.
10. If the command times out but a Python process or output file suggests work may still be running, inspect and wait; do not announce a final result early.
11. During long waits, reassure the user that image2 can take a few minutes and that you are still waiting for the actual result.
12. After completion, report the saved file path. For failures, report the HTTP status, returned message, and a short explanation.

## 4K And Custom Size Rules

The actual output size is controlled by the `--size` parameter. Writing "4K" or "high resolution" only in the prompt is not enough.

Before sending a 4K or custom-size request, make sure the requested `WIDTHxHEIGHT` satisfies all of these constraints:

- The long edge must be no more than `3840` pixels.
- Both width and height must be multiples of `16`.
- The aspect ratio must be no more extreme than `3:1`.
- Total pixels must be between `655360` and `8294400`.

Useful examples:

- `3840x2160` is valid landscape 4K.
- `2160x3840` is valid portrait 4K.
- `4096x2160` is invalid because the long edge is greater than `3840`.
- `4096x4096` is invalid because the long edge and total pixels exceed the limits.

If a user asks for an invalid 4K size, explain the rule and suggest the closest valid size, such as `3840x2160`, `2160x3840`, or `2048x2048`.

Even valid 4K requests are heavy and may fail with gateway or timeout errors. If a valid 4K request fails, tell the user that 4K generation can genuinely fail on this channel due to upstream timeout or capacity limits, then include the actual HTTP status and message.

## Commands

Generate:

```powershell
$env:IMAGE2_API_KEY="sk-..."
python <skill_dir>\scripts\image2_cli.py generate "final prompt here" --size 2048x2048 --quality high --slug short-request-slug --timeout 600
```

Edit:

```powershell
$env:IMAGE2_API_KEY="sk-..."
python <skill_dir>\scripts\image2_cli.py edit "edit instruction here" --input .\source.png --size 2048x2048 --quality high --slug edited-output-slug
```

If `python` is unavailable, try `py -3` on Windows or `python3` on Unix-like systems. If no Python runtime is available, help the user install one using the environment's normal package manager, then rerun. If `httpx` is unavailable, install it with `python -m pip install httpx` before retrying.

## Failure Notes

- `502 Bad Gateway`, `504`, `522`, or `524`: the image channel or upstream service timed out or returned a gateway error. The script retries these by default.
- `503` with a message like `No available compatible accounts`: the channel currently has no compatible image account available, or the key/group cannot use this model.
- `401` or `403`: likely invalid key, missing permission, or wrong group.
- Local file errors in edit mode usually mean the input path is missing or not readable.
- For valid 4K sizes such as `3840x2160`, `502` or `524` can still happen because 4K generation is slow and resource-heavy on this channel.

Always wait for concrete script feedback before giving the user a conclusion.

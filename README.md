# screenscan

> **💡 Strongly recommended: set this up with an AI agent such as the [Claude app](https://claude.com/download) or the Codex app.** Open this project folder in the agent and ask it to "follow the README and set this up for me". It can install the tools, fix problems as they come up and run the analysis for you. Keep your API key out of the chat: paste it into the `.env` file yourself (step 5).

Finds every time a screen appears in a TV episode (computer, TV, projector, phone and so on) and saves **one best 1920×1080 screenshot per appearance**. It produces:

- a folder of PNG screenshots for each episode,
- `screens.xlsx`: a spreadsheet with the episode, air date, `MM:SS` timestamp and an embedded thumbnail for each screenshot,
- `review.html`: a web page to flip through every screenshot and check it by hand.

Only screens that are switched on **and** whose content is readable are kept. Readable screens in the background count too. When the software is unsure, it keeps the frame, because a stray false positive is easier to delete by hand than a missed screen is to find.

It is currently set up for *Degrassi: The Next Generation*, **Season 1** and **Season 7** (see [step 6](#6-put-your-video-files-in-place)).

---

## How it works (short version)

Most of the work happens on your own computer. Only a small number of still images are sent to an online AI service to be examined.

| Stage | What it does | Where it runs |
|---|---|---|
| `sample` | Grabs 2 frames per second from each episode | your computer |
| `siglip` | Scores every frame for "is there a screen?" | your computer |
| `shared` | Skips recurring footage such as the title sequence and credits | your computer |
| `detect` | Finds small background screens | your computer |
| `verify` | An AI model looks at the promising frames and lists the screens in them | **OpenRouter (online)** |
| `refine` | The AI takes a second, closer look at a crop of each screen found | **OpenRouter (online)** |
| `select` | Groups frames into appearances and picks the best frame of each | your computer |
| `export` | Writes the full-size PNGs, the spreadsheet and the review page | your computer |

> **Privacy:** the frames sent in `verify` and `refine` leave your computer and are processed by OpenRouter and the model provider it routes to. Do not use this on footage you are not allowed to send to a third party.

---

## Setup, step by step

### 1. What you need

- A **Mac with Apple silicon**, a **Linux** machine, or Windows via WSL. Linux with an NVIDIA GPU is the fastest and the best tested. **macOS has not been tested yet**, so expect to report problems.
- About **20–25 GB of free disk space per season** for intermediate files (sampled frames and so on), on top of the space your video files take.
- An internet connection. The first run downloads two AI models (several GB) from Hugging Face.
- The episodes as video files (`.mkv`). **You must provide these yourself; they are not included.**
- A credit or debit card for OpenRouter (see step 3).

### 2. Install `git` and `uv`

`uv` is the tool that installs Python and every library for you. You do not need to install Python yourself.

**On a Mac**, open the **Terminal** app and run:

```bash
xcode-select --install     # installs git, if you don't have it (a window will pop up)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then **close the Terminal window and open a new one**, so `uv` is found. (If you use Homebrew, `brew install uv` works too.)

**On Linux**:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

(install `git` with your package manager if it is missing), then open a new terminal.

Check that both work:

```bash
git --version
uv --version
```

### 3. Get the code

```bash
git clone https://github.com/grishnakov/screen_shots.git
cd screen_shots
```

All the commands below are run from inside this `screen_shots` folder.

### 4. Create an OpenRouter account, add credit, and make an API key

The AI model that reads the frames is accessed through [OpenRouter](https://openrouter.ai), a service that charges per use. You need an **API key** (a long password that identifies your account) and some **credit** on the account.

1. Go to **<https://openrouter.ai>** and sign up (or log in).
2. Add money to your account on the **Credits** page: <https://openrouter.ai/settings/credits>.
   - OpenRouter accepts major credit cards, AliPay and crypto (USDC). Card payments carry a fee of 5.5% with a $0.80 minimum, so very small top-ups are proportionally more expensive.
   - **This tool is cheap.** As measured on a full season of 14 episodes, the AI cost was roughly **$0.50 per season**, or about **$0.003 per screenshot found**. Adding **$5** is plenty for several seasons.
   - Without credit the requests are refused (you will see a `402` error or "insufficient credits").
3. Open **<https://openrouter.ai/workspaces/default/keys>** and **generate an API key**. Give it any name you like, for example `screenscan`.
4. **Copy the key immediately** and keep it somewhere safe. It starts with `sk-or-`. You may not be able to view it again later; if you lose it, create a new one.

> Treat the key like a password. Anyone who has it can spend your credit. Never post it in a chat, an issue, a screenshot, or commit it to git.

### 5. Create your `.env` file ⚠️ do these two steps in this order

The project comes with a settings file called **`.env.template`**. It has no key in it and cannot be used as it is.

> ## ⚠️ Step A: **rename `.env.template` to `.env`**
>
> ```bash
> mv .env.template .env
> ```
>
> ## ⚠️ Step B: **only after that**, put your API key into `.env`
>
> Open the new `.env` file in any text editor:
>
> ```bash
> open -e .env        # macOS: opens it in TextEdit
> nano .env           # Linux (or macOS): Ctrl+O then Enter to save, Ctrl+X to exit
> ```
>
> Find the line
>
> ```
> VLM_API_KEY=
> ```
>
> and paste your key **directly after the `=`**, with no spaces and no quotes:
>
> ```
> VLM_API_KEY=sk-or-xxxxxxxxxxxxxxxxxxxxxxxx
> ```
>
> Save the file.

Common mistakes:

- **Pasting the key into `.env.template`.** That file is the blank template and is not read by the program. The program only reads a file named exactly `.env`.
- **Forgetting the dot.** The name is `.env`, not `env` and not `env.txt`.
- **Not seeing the file.** Names that start with a dot are hidden in Finder and most file browsers. Use the Terminal commands above, or press `Cmd`+`Shift`+`.` in Finder to show hidden files.
- **Spaces or quotes around the key.** It must look exactly like `VLM_API_KEY=sk-or-...`.

The other two lines in `.env` (`VLM_BASE_URL` and `VLM_MODEL`) are already set to OpenRouter and the `deepseek/deepseek-v4.1-flash` model. You do not need to change them.

`.env` is excluded from git, so your key cannot be committed by accident.

### 6. Put your video files in place

The project already contains a `video/` folder. Copy your `.mkv` files into it. The program finds each episode by a tag in the **file name** such as `S01E03` (season 1, episode 3), so name your files like this:

```
video/S01E03 - Family Politics.mkv
video/Show.Name.s02e10.1080p.mkv
```

**[`video/README.md`](video/README.md) has the full naming rules, examples of names that do not work, and a command to check that your files are recognised.** Files without a tag are skipped with a warning.

Episode titles and air dates (taken from Wikipedia) currently come from a built-in list that only contains *Degrassi: The Next Generation* Seasons 1 and 7. A tag for any other episode stops the run with a clear message. In that list, Season 1 episodes 1 and 2 are one 42-minute premiere (*Mother and Child Reunion*), so use `S01E01` for it; there is no `S01E02`.

### 7. Run it

Pick the season with `SEASON=`. To try it on a single episode first (recommended), for example Season 1, episode 3:

```bash
SEASON=1 ./run.sh 3
```

Run a few episodes:

```bash
SEASON=1 ./run.sh 3 4 5
```

Run the whole season:

```bash
SEASON=1 ./run.sh
```

(If you see `permission denied`, run `bash run.sh` instead of `./run.sh`, for example `SEASON=1 bash run.sh 3`.)

The first run takes a while: `uv` installs everything, then the two models are downloaded, and then the stages run one after another. The screen shows a line such as `=== 22:10:03 verify` as each stage starts.

**It is safe to stop and restart.** Every stage saves its results and skips work that is already done, so if the run is interrupted (Ctrl+C, a closed laptop, lost internet), just run the same command again and it carries on.

### 8. Look at the results

Everything ends up in `output/season01/` (or `season07` for Season 7):

```
output/season01/
  review.html        <- open this in your web browser first
  screens.xlsx       <- the spreadsheet
  S01E03_Family_Politics/
      S01E03_Family_Politics_05-07.png   <- one screenshot per screen appearance, named by its MM-SS timestamp
      ...
```

Open `review.html` by double-clicking it, or run `open output/season01/review.html` on a Mac. Each PNG's file name ends in its timestamp as `MM-SS` (a colon can't be used in file names), and the spreadsheet shows it as `MM:SS`.

Running a subset of episodes rewrites `screens.xlsx` and `review.html` with **only those episodes**. Run the whole season (or the same set of episodes) again to get a complete sheet.

---

## Troubleshooting

| Symptom | What it means / what to do |
|---|---|
| `VLM_API_KEY is not set: copy .env.template to .env and add your key` | You skipped step 5, or the file is not named exactly `.env`, or the key line is empty. |
| Lines like `VLM error on job 12: ... 401 ...` | The key is wrong or was revoked. Create a new key and update `.env`. |
| `... 402 ...` or "insufficient credits" | Your OpenRouter balance is empty. Add credit on <https://openrouter.ai/settings/credits>, then run the same command again. |
| A few `VLM error on job N` lines, then the run continues | Normal for the occasional network hiccup or bad response. Failed items are not saved, so they are retried automatically the next time you run the same command. |
| `Event loop is closed` messages | Harmless noise from closing network connections. Ignore them. |
| `uv: command not found` | Close and reopen the terminal after installing `uv`. |
| Out of disk space | Each season needs about 20–25 GB in the `work/` folder. After the output is finished and checked you may delete `work/` to reclaim space (you will have to recompute everything if you run that season again). |
| Slow on a Mac | Expected: the local stages run on the Apple GPU (or the CPU) instead of an NVIDIA card. To force the CPU if you see GPU errors: `SCREENSCAN_DEVICE=cpu SEASON=1 ./run.sh 3`. |

## Good to know

- **Accuracy:** expect some false positives (lit vending machines, menu boards and similar) and a few misses of blurry or tiny screens. Always skim `review.html` and delete what you don't want.
- **Older footage is softer**, so small on-screen text can be harder to read in Season 1.
- **Using a different AI backend:** any OpenAI-compatible service that accepts images works. Change `VLM_BASE_URL`, `VLM_MODEL` and `VLM_API_KEY` in `.env`. `.env` also has a commented-out block for a local vLLM server (Linux with an NVIDIA GPU only).
- **Tuning:** the thresholds live at the top of `screenscan/select.py` (`APPEARANCE_GAP_S`, `APPEARANCE_MIN_SIM`) and `screenscan/verify.py` (`MARGIN_THRESHOLD`, `OWL_THRESHOLD`).
- **Running one stage on its own:** `SEASON=1 uv run -m screenscan.verify 3` (stages: `sample`, `siglip`, `shared`, `detect`, `verify`, `refine`, `select`, `export`).

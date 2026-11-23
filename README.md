# Flake Scanner — flake angle statistics on the forming line, built without a Mac

**Status (Nov 23, 2026): planning.** Requirements, design and the implementation plan are in [`docs/`](docs/). No app build exists yet; this guide grows with each phase.

## What the app will do

- A phone mounted above the forming line looks straight down at the mat. You drag a box on the live picture to choose the **region of interest**; only that region is measured.
- You choose how many **shots per second** are analyzed. Accuracy comes first: if the phone cannot keep up, it analyzes fewer shots and shows the rate it achieved.
- The app finds the **machine direction** from the mat's movement and measures the angle of every flake edge to it: mean angle, spread, alignment, orientation factor, percent within ±10/20/30°, histogram and rose plot, trends over time, with confidence intervals.
- **Quality checks** (exposure, focus, motion blur, lighting flicker, level) mark frames that would bias the result and leave them out, with the reason.
- **Runs** are saved as CSV and JSON (plus optional frame pictures) that open in Excel, and are visible in the Files app.
- A **second iPhone** with the app controls the scanner over a direct phone-to-phone Wi-Fi link, like Phone LiDAR's remote: pair with a code, see the live picture, draw the region, start and stop, change settings, read the statistics, copy runs.

## Building and installing (same as Phone LiDAR)

1. **GitHub repository** — to be created by the owner (suggested name `FlakeScanner`; public gives free macOS build minutes). Not created yet.
2. **Cloud build** — GitHub Actions compiles the app on a `macos-26` runner and produces `FlakeScanner-unsigned-ipa-<run>` (from phase P0).
3. **Install** — with Sideloadly and a free Apple ID (re-sign every 7 days) or through TestFlight (paid Apple Developer Program), exactly as for Phone LiDAR.

## Mounting and lighting (preliminary, from the design's error budget)

- Camera pointing straight down: the level turns amber above 1° and red above 3° of tilt.
- Keep the region of interest near the middle of the picture: with the phone tilted, a region off to one side adds a bias (up to 0.6° at 3° of tilt).
- Phone in portrait with the mat moving across the screen (right ↔ left), as with Phone LiDAR. The movement then runs along the camera's readout, and the rolling shutter only stretches or squeezes the picture along the travel by about 1.5–3 %, so spreads and angles away from the machine direction read that much too small or large (the app shows the factor). Mounted the other way, the picture is sheared and the mean angle moves; the app warns.
- Light the mat evenly from both sides or along the camera axis; light from one side shifts the mean angle by about 2°.
- Flicker-free (DC-driven) LED light: dimmed LEDs make bands across the picture with short shutters, and mains flicker changes the brightness from shot to shot. The app detects both and warns; steady light is the real fix.
- Enough light for a short shutter: the mat may move at most about one pixel during the exposure, so the shutter must be no longer than the millimetres per pixel divided by the line speed, for example 1/4,200 s at 1,500 mm/s with 0.36 mm per pixel (camera about 1 m above the mat). That takes about 2,000 lux on the mat, more than most halls have, so plan for an added LED light. Motion blur pulls angles toward the machine direction.
- Before the first run on a mount, measure the flake width by dragging across a few typical flakes; the app needs it, and a width set too small makes the spread read too high.

## Developer documentation

- [Requirements](docs/requirements.md), [design](docs/design.md), [implementation plan and change log](docs/implementation-plan.md), [agent rules](CLAUDE.md).
- [Algorithm lab](tools/lab/README.md): synthetic flake mats and estimator comparisons in Python.

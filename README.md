# Flake Scanner — flake angle statistics on the forming line, built without a Mac

**Status (Nov 23, 2026):** the first app build compiles and installs. It is a shell with Home and About; nothing measures yet. Requirements, design and the implementation plan are in [`docs/`](docs/). This guide grows with each phase.

## What the app will do

- A phone mounted above the forming line looks straight down at the mat. You drag a box on the live picture to choose the **region of interest**; only that region is measured.
- You choose how many **shots per second** are analyzed. Accuracy comes first: if the phone cannot keep up, it analyzes fewer shots and shows the rate it achieved.
- The app finds the **machine direction** from the mat's movement and measures the angle of every flake edge to it: mean angle, spread, alignment, orientation factor, percent within ±10/20/30°, histogram and rose plot, trends over time, with confidence intervals.
- **Quality checks** (exposure, focus, motion blur, lighting flicker, level) mark frames that would bias the result and leave them out, with the reason.
- **Runs** are saved as CSV and JSON (plus optional frame pictures) that open in Excel, and are visible in the Files app.
- A **second iPhone** with the app controls the scanner over a direct phone-to-phone Wi-Fi link, like Phone LiDAR's remote: pair with a code, see the live picture, draw the region, start and stop, change settings, read the statistics, copy runs.

## Building and installing

You need a Windows PC, an iPhone (iOS 17 or newer), a USB cable and a free GitHub account. You do not need a Mac. GitHub rents the Apple hardware that compiles the app.

### 1. Repository

The code is at https://github.com/AliG1111/FlakeScanner. The repository is public, so the macOS build minutes are free.

### 2. Cloud build

The workflow is called **Build iOS app**. It runs:

- for every pull request into `main`,
- for every push to `main` that changes more than Markdown files,
- by hand: **Actions › Build iOS app › Run workflow**.

Each run has two jobs: `unsigned-ipa` (builds the app) and `unit-tests`. Both must be green.

To get the app, open the finished run and scroll to **Artifacts**. Download `FlakeScanner-unsigned-ipa-<run>`. It is a zip with the `.ipa` inside. Unzip it.

The build number of the app is the run number. Run 12 gives `FlakeScanner-unsigned-ipa-12` and build 12. Artifacts are kept for 30 days.

### 3. Install

Pick one way.

**A. Sideloadly with a free Apple ID.** The app must be re-signed every 7 days.

1. On Windows, install **iTunes** (apple.com/itunes/download/win64) and the non-Store **iCloud** installer. The Microsoft Store versions do not work. Then install **Sideloadly** from sideloadly.io.
2. Plug in the iPhone, unlock it and tap **Trust This Computer**.
3. Open Sideloadly, drag the `.ipa` onto it, enter your Apple ID and click **Start**. Enter the password and 2FA code when asked.
4. On the iPhone, open **Settings › General › VPN & Device Management**, tap your Apple ID under **DEVELOPER APP** and tap **Trust**.
5. Open **Settings › Privacy & Security › Developer Mode**, turn it on, restart the phone and confirm.
6. After 7 days the app stops opening. Drag a newer `.ipa` (or the same one) into Sideloadly with the same Apple ID. Saved data stays.

**B. TestFlight with a paid Apple Developer Program account (99 USD a year).** Builds stay installable for 90 days and install over the air.

One-time setup, in a web browser:

1. Enroll at developer.apple.com/programs.
2. At developer.apple.com, under **Certificates, IDs & Profiles › Identifiers**, add an App ID with the bundle ID `ca.gervais.flakescanner`. If it is taken, pick another and change `PRODUCT_BUNDLE_IDENTIFIER` for the `FlakeScanner` target in `project.yml` (the test target uses `ca.gervais.flakescanner.tests`).
3. At appstoreconnect.apple.com, add a new iOS app with that bundle ID.
4. In App Store Connect, under **Users and Access › Integrations › App Store Connect API**, create a team key with **App Manager** access. Note the Issuer ID and the Key ID. Download the `.p8` key file (you can download it only once).
5. In PowerShell, make a certificate private key: `ssh-keygen -t rsa -b 2048 -m PEM -f cert_key`. Press Enter twice for an empty passphrase. Never commit these files.
6. In the repository, open **Settings › Secrets and variables › Actions** and add four repository secrets:

   | Name | Value |
   |---|---|
   | `APP_STORE_CONNECT_ISSUER_ID` | The Issuer ID from step 4 |
   | `APP_STORE_CONNECT_KEY_IDENTIFIER` | The Key ID from step 4 |
   | `APP_STORE_CONNECT_PRIVATE_KEY` | The full text of the `.p8` file, with the BEGIN and END lines |
   | `CERTIFICATE_PRIVATE_KEY` | The full text of `cert_key` from step 5 |

For each TestFlight build:

1. Open **Actions › Build iOS app › Run workflow**, tick the `testflight` input (**Also sign and upload to TestFlight**) and run it. The `testflight` job starts only after `unsigned-ipa` and `unit-tests` have passed.
2. Wait for App Store Connect to process the build (5 to 30 minutes).
3. In App Store Connect, open the app, then **TestFlight › Internal Testing**, make a group and add yourself. Install the **TestFlight** app on the iPhone and install Flake Scanner from it.

The job also keeps the signed `.ipa` as the artifact `FlakeScanner-signed-ipa-<run>`.

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

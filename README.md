# Flake Scanner — flake angle statistics on the forming line, built without a Mac

**Status (Nov 23, 2026):** the first app build compiles and installs. It is a shell with Home and About; nothing measures yet. Requirements, design and the implementation plan are in [`docs/`](docs/). This guide grows with each phase.

## What the app will do

- A phone mounted directly above the forming line looks straight down at the mat; its LiDAR measures the height, so speeds and sizes can be given in millimetres. You drag a box on the live picture to choose the **region of interest**; only that region is measured.
- You choose how many **shots per second** are analyzed. Accuracy comes first: if the phone cannot keep up, it analyzes fewer shots and shows the rate it achieved.
- The app finds the **machine direction** from the mat's movement and measures the angle of every flake edge to it: mean angle, spread, alignment, orientation factor, percent within ±10/20/30°, histogram and rose plot, trends over time, with confidence intervals.
- **Quality checks** (exposure, focus, motion blur, lighting flicker, level) mark frames that would bias the result and leave them out, with the reason.
- **Runs** are saved as CSV and JSON (plus optional frame pictures) that open in Excel, and are visible in the Files app. Leave a run's folder alone while it is recording: if it is moved or deleted, the run stops.
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

Each run has two jobs: `unsigned-ipa` (builds the app) and `unit-tests`. Both must be green. The `.ipa` is made even if `unit-tests` fails, so install only from a run where both jobs are green.

To get the app, open the finished run and scroll to **Artifacts**. Download `FlakeScanner-unsigned-ipa-<run>`. It is a zip with the `.ipa` inside. Unzip it.

The build number of the app is the run number. Run 12 gives `FlakeScanner-unsigned-ipa-12` and build 12. The `.ipa` artifact is kept for 30 days.

If a job fails, the run's summary page lists the compiler errors (**Build errors**) or the failed tests. Two more artifacts help: `build-log-<run>` (the full logs of the app job, kept 14 days) and `unit-test-results-<run>` (only when the `unit-tests` job fails: the test results and logs, kept 14 days).

### 3. Install

Pick one way.

**A. Sideloadly with a free Apple ID.** The app must be re-signed every 7 days.

1. On Windows, install **iTunes** (apple.com/itunes/download/win64) and the non-Store **iCloud** installer. The Microsoft Store versions do not work. Uninstall them first, and also the Store apps *Apple Devices*, *Apple Music* and *Apple TV*, which stop iTunes from seeing the phone. Then install **Sideloadly** from sideloadly.io.
2. Plug in the iPhone, unlock it and tap **Trust This Computer**.
3. Open Sideloadly, drag the `.ipa` onto it, enter your Apple ID and click **Start**. Enter the password and 2FA code when asked.
4. On the iPhone, open **Settings › General › VPN & Device Management**, tap your Apple ID under **DEVELOPER APP** and tap **Trust**.
5. Open **Settings › Privacy & Security › Developer Mode**, turn it on, restart the phone and confirm.
6. After 7 days the app stops opening. Drag a newer `.ipa` (or the same one) into Sideloadly with the same Apple ID. Saved data stays.

A free Apple ID allows only 3 sideloaded apps at a time and 10 new App IDs per 7 days. This matters if Phone LiDAR is installed too.

**B. TestFlight with a paid Apple Developer Program account (99 USD a year).** Builds stay installable for 90 days and install over the air.

One-time setup, in a web browser:

1. Enroll at developer.apple.com/programs.
2. At developer.apple.com, under **Certificates, IDs & Profiles › Identifiers**, add an App ID with the bundle ID `ca.gervais.flakescanner`. If it is taken, pick another and change `PRODUCT_BUNDLE_IDENTIFIER` for the `FlakeScanner` target in `project.yml` (the test target uses `ca.gervais.flakescanner.tests`).
3. At appstoreconnect.apple.com, add a new iOS app with that bundle ID. The app name must be unique in App Store Connect: any unique name works. The SKU can be anything.
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
- Keep the region of interest near the middle of the picture: with the phone tilted, a region off to one side adds a bias. At 3° of tilt that is up to about 0.6° for a region a third of the way to the edge and about 2° at the edge; the scan screen shows the bound for your region.
- Phone in portrait with the mat moving across the screen (right ↔ left), as with Phone LiDAR. The movement then runs along the camera's readout, and the rolling shutter only stretches or squeezes the picture along the travel by about 1–2 %, so spreads and angles away from the machine direction read that much too small or large (the app shows the factor). Mounted the other way, the picture is sheared and the mean angle moves; the app warns.
- Light the mat evenly from both sides or along the camera axis; light from one side shifts the mean angle by about 2°.
- Flicker-free (DC-driven) LED light: dimmed LEDs make bands across the picture with short shutters, and many mains-powered lights flicker 100 or 120 times a second. The app checks the light for about a second after you press Start and warns (*Light flickers*), watches for brightness changes during it (*Light changed*), and leaves out shots with bands (*Light bands*). *Flake edges* cannot be corrected for bands and leaves out every banded shot, even faintly banded ones, while *Edge orientation* corrects most of them, so under banded light make *Edge orientation* the method (with *Both*, the primary one). Bad light mostly costs shots, but bands too faint to detect can still shift angles a little, so steady light is the real fix. On a layer whose strands run from the top to the bottom of the screen (usually the core layer), *Flake edges* also leaves out about half of the shots under steady light, and the shots it keeps can shift its result by up to about 0.3°, so make *Edge orientation* the primary method there as well.
- Keep the region of interest on the mat. If *Light bands* appears under steady light, look for a dark shadow or edge running from the top to the bottom of the screen through the box (the shadow of a cross member, a belt edge, a guide) and move the box or the phone so that it stays out. Make the box at least three flake lengths tall: a shorter box is more often taken for banded.
- Enough light for a short shutter: the mat may move at most about one pixel during the exposure, so the shutter must be no longer than the millimetres per pixel divided by the line speed, for example 1/2,800 s at 1,000 mm/s with 0.36 mm per pixel (camera about 1 m above the mat). That takes about 1,300 lux on the mat, more than most halls have, so plan for an added LED light. Motion blur pulls angles toward the machine direction.
- The light differs from place to place. Before and during a run the app tells you whether the results will be good, fair or poor for the line speed and the light, and what would help (about how many times more light, a slower line or a higher mount, or steady light when bands cost many shots); *Poor* shows a banner. Setup also shows the forecast for the highest line speed you expect (set under *Advanced*; 1,000 mm/s unless you change it), so you can judge a mount before the line reaches full speed.
- The camera height may differ from mount to mount: the app measures it with the LiDAR for about a second when you press Start (keep the box on the mat), and you can type it in if the LiDAR gets no reading.
- Before the first run on a mount, measure the flake width by dragging across a few typical flakes; the app needs it, and a width set too small makes the spread read too high. The app keeps the width with the camera and picture size it was measured on: it adjusts it when you change the picture size or the camera height and asks again when you change the camera.

## Developer documentation

- [Requirements](docs/requirements.md), [design](docs/design.md), [implementation plan and change log](docs/implementation-plan.md), [agent rules](CLAUDE.md).
- [Algorithm lab](tools/lab/README.md): synthetic flake mats and estimator comparisons in Python.

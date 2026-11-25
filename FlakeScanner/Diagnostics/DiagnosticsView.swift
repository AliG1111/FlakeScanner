import SwiftUI

/// Settings › Diagnostics (FR-APP-06): the probe for the phone and the plant (UC-09).
struct DiagnosticsView: View {
    @StateObject private var model = DiagnosticsModel()

    var body: some View {
        Form {
            Section("Setup") {
                Picker("Shutter limit", selection: $model.shutterDenominator) {
                    ForEach(DiagnosticsModel.shutterChoices, id: \.self) { Text("1/\($0) s").tag($0) }
                }
                Picker("Region width", selection: $model.roiWidthPercent) {
                    ForEach(DiagnosticsModel.roiWidthChoices, id: \.self) { Text("\($0) % of the frame").tag($0) }
                }
                Picker("Format", selection: $model.formatIndex) {
                    Text("Best (default)").tag(-1)
                    ForEach(model.formatOptions, id: \.index) { Text($0.text).tag($0.index) }
                }
                Stepper("Sample frames: \(model.sampleFrames)", value: $model.sampleFrames, in: 2...30)
                Text("Hold the phone where it will hang over the mat, looking straight down. The region is the centre of the frame (80 % of its height).")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            Section("Tests") {
                testButton("Camera report", "Formats, binning, distortion correction, ISO and exposure ranges.", model.cameraReport)
                testButton("Sample frames", "Real pictures of the region with the camera data of each frame.", model.sampleCapture)
                testButton("Light check", "Flicker of the light: 1 s burst, about 2 s in all.", model.lightCheck)
                testButton("Readout test", "Two bursts; you turn the phone half a turn in between. Point at a still, evenly lit surface.", model.readoutTest)
                testButton("Noise series", "Two pictures at each ISO on a still surface (about 30 s).", model.noiseSeries)
                HStack {
                    Text("Tape measure (mm)")
                    Spacer()
                    TextField("optional", text: $model.tapeMeasureText)
                        .keyboardType(.decimalPad)
                        .multilineTextAlignment(.trailing)
                        .frame(maxWidth: 120)
                }
                testButton("LiDAR probe", "Camera switch times, what the LiDAR camera accepts, distance at the region and the corners.", model.lidarProbe)
            }
            if model.isBusy || model.prompt != nil {
                Section("Running") {
                    if let prompt = model.prompt {
                        Text(prompt).bold()
                        Button("Continue") { model.continueAfterPrompt() }
                            .buttonStyle(.borderedProminent)
                    } else {
                        HStack(spacing: 12) {
                            ProgressView()
                            Text(model.status)
                        }
                    }
                }
            }
            if model.cameraDenied {
                Section {
                    Text("The camera is off for Flake Scanner.")
                    Button("Open Settings") { CameraAccess.openSettings() }
                }
            }
            if let error = model.errorText {
                Section("Problem") {
                    Text(error).foregroundStyle(.red)
                }
            }
            if !model.resultText.isEmpty {
                Section("Result") {
                    Text(model.resultText)
                        .font(.system(.footnote, design: .monospaced))
                        .textSelection(.enabled)
                }
            }
            Section("Files") {
                Text("\(model.storage.files) files, \(Units.bytes(model.storage.bytes)) in Files › Flake Scanner › Diagnostics. They stay on this phone until you share them.")
                    .font(.footnote)
                if let url = model.zipURL {
                    ShareLink(item: url) {
                        Label("Share the zip", systemImage: "square.and.arrow.up")
                    }
                } else {
                    Button {
                        model.prepareZip()
                    } label: {
                        Label("Make the zip to share", systemImage: "doc.zipper")
                    }
                    .disabled(model.isBusy || model.storage.files == 0)
                }
                Button(role: .destructive) {
                    model.deleteAll()
                } label: {
                    Label("Delete all results", systemImage: "trash")
                }
                .disabled(model.isBusy || model.storage.files == 0)
            }
        }
        .navigationTitle("Diagnostics")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear { model.refreshStorage() }
    }

    private func testButton(_ title: String, _ caption: String, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.headline)
                Text(caption).font(.caption).foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
        }
        .disabled(model.isBusy)
    }
}

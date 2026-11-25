import SwiftUI

/// Home (FR-APP-01): Scan, Connect to the other phone, Runs and Settings / About. Only Settings (Diagnostics and
/// About) works in this build; the other three are placeholders until their screens exist.
struct HomeView: View {
    var body: some View {
        NavigationStack {
            List {
                Section {
                    PlaceholderRow(title: "Scan", systemImage: "camera.viewfinder")
                    PlaceholderRow(title: "Connect to the other phone", systemImage: "iphone.radiowaves.left.and.right")
                    PlaceholderRow(title: "Runs", systemImage: "folder")
                }
                Section {
                    NavigationLink {
                        SettingsView()
                    } label: {
                        HomeRowLabel(title: "Settings / About",
                                     systemImage: "gearshape",
                                     caption: "Diagnostics, version and build number")
                    }
                }
            }
            .navigationTitle("Flake Scanner")
        }
    }
}

/// An entry that is not available yet: dimmed and not tappable, with a caption saying so.
private struct PlaceholderRow: View {
    let title: String
    let systemImage: String

    var body: some View {
        Button {
            // Nothing to open yet.
        } label: {
            HomeRowLabel(title: title, systemImage: systemImage, caption: "Comes in a later build")
        }
        .disabled(true)
    }
}

private struct HomeRowLabel: View {
    let title: String
    let systemImage: String
    let caption: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: systemImage)
                .font(.title2)
                .frame(width: 32)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.headline)
                Text(caption)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 6)
        .frame(minHeight: 44, alignment: .leading)
    }
}

/// App name, version and build number, what the app does, and a link to the user guide.
struct AboutView: View {
    /// The user guide (README) in the public repository.
    private static let userGuideURL = URL(string: "https://github.com/AliG1111/FlakeScanner#readme")

    private var versionText: String {
        AppInfo.versionText(Bundle.main.infoDictionary ?? [:])
    }

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Flake Scanner")
                        .font(.title2.bold())
                    Text(versionText)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 4)
                .accessibilityElement(children: .combine)
            }
            Section {
                Text("Measures the angle of the strands on an OSB forming line, with live and recorded statistics.")
            }
            if let guideURL = Self.userGuideURL {
                Section {
                    Link(destination: guideURL) {
                        Label("User guide", systemImage: "book")
                    }
                }
            }
        }
        .navigationTitle("About")
        .navigationBarTitleDisplayMode(.inline)
    }
}

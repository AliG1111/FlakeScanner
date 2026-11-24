import SwiftUI

/// Settings / About: Diagnostics (the probe) and About. More settings arrive with the scan screens.
struct SettingsView: View {
    var body: some View {
        List {
            Section {
                NavigationLink {
                    DiagnosticsView()
                } label: {
                    Label("Diagnostics", systemImage: "stethoscope")
                }
                NavigationLink {
                    AboutView()
                } label: {
                    Label("About", systemImage: "info.circle")
                }
            }
        }
        .navigationTitle("Settings")
        .navigationBarTitleDisplayMode(.inline)
    }
}

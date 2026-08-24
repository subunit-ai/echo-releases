# Echo — Releases

Offizielle Download- und Auto-Update-Distribution für **Echo** (Subunit).

Dieses Repository enthält ausschließlich signierte, kompilierte Installer und das
Updater-Manifest (`latest.json`). Der Quellcode ist proprietär und nicht Teil
dieses Repositories.

**Downloads:** [Releases](../../releases/latest) — macOS (Apple Silicon), Windows x64, Windows ARM64, Linux x86_64.

**Auto-Update-Feed:** `https://github.com/subunit-ai/echo-releases/releases/latest/download/latest.json`

Echo-Releases enthalten ausschließlich die Diktat-Engine (`local-whisper` bzw.
`local-whisper-gpu`). Meeting-Aufzeichnung, Diarisierung und Voiceprints gehören
zum eigenständigen SCAI-Meet-Plugin und sind kein Echo-Releasebestandteil mehr.

Auch Alpha-Tags wie `v0.5.164-alpha.5` werden bewusst als **normale GitHub-Releases**
veröffentlicht und als `Latest` markiert. Damit läuft der normale Echo-Updater immer
über genau denselben Kanal; es gibt keinen separaten Prerelease-Kanal.

© Subunit. Alle Rechte vorbehalten.

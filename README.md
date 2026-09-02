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

Automatische Poller bauen ausschließlich suffixlose Stable-Tags wie `v0.5.166`;
dieser Kanal veröffentlicht weiterhin atomar als normalen GitHub-`Latest` und
speist Echos Standard-Updater.

Ein signierter Testkandidat kann ausschließlich manuell mit `release_mode=draft_rc`
und einem exakt passenden Tag wie `v0.5.166-rc.1` gebaut werden. Er bleibt als
nicht öffentlich gelisteter GitHub-Draft mit gesetztem Prerelease-Merkmal bestehen
und wird niemals `Latest`. Dadurch kann er von einem Maintainer geprüft und manuell
installiert werden, ohne reguläre Echo-Installationen zu aktualisieren.

© Subunit. Alle Rechte vorbehalten.

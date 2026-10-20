Minimal stand-ins for the Omarchy shell's QML modules, used only by
`tests/test_plugin_qml.py` and `qmllint`. They copy the property and signal
names that the real `qs.Ui` components expose (as read from the Omarchy `quattro`
sources) and nothing else, so a typo in the plugin's QML fails here instead of
inside a user's running shell.

They are not the real shell. A passing run proves the plugin's own QML parses,
resolves its names against these interfaces and behaves as intended; it does
not prove the live shell loads it.

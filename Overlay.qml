// Summon target for Kumquat.
//
//   omarchy-shell shell summon io.github.sulaimanbaeisa.kumquat '{}'
//   omarchy-shell shell summon io.github.sulaimanbaeisa.kumquat \
//       '{"files": ["/home/me/photo.jpg"], "tab": "conversions"}'
//
// Kumquat is its own GTK 4 window, so this entry point draws nothing: it starts
// bin/kumquat and then asks the shell to close it again. The payload is
// optional; see Launch.parseRequest() for what it accepts.
import QtQuick
import Quickshell
import "Launch.js" as Launch

Item {
  id: root

  // The shell assigns these when they are declared.
  property string omarchyPath: ""
  property var shell: null
  property var manifest: null

  property bool opened: false

  readonly property string pluginId: manifest && manifest.id ? String(manifest.id) : Launch.pluginId()
  readonly property string launcher: Launch.urlToPath(Qt.resolvedUrl("bin/kumquat"))

  function open(payloadJson) {
    opened = true
    const request = Launch.parseRequest(payloadJson)
    for (let i = 0; i < request.problems.length; i++)
      console.warn("[kumquat] " + request.problems[i])
    if (launcher === "")
      console.warn("[kumquat] cannot locate bin/kumquat from " + Qt.resolvedUrl("bin/kumquat"))
    else
      Quickshell.execDetached(Launch.launchCommand(launcher, request))
    // Closing from inside open() would unload this item while the shell is
    // still delivering the payload to it.
    Qt.callLater(dismiss)
  }

  function close() {
    opened = false
  }

  function dismiss() {
    opened = false
    if (shell && typeof shell.hide === "function")
      shell.hide(pluginId)
  }
}

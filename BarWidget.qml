// Bar button that opens Kumquat's file picker.
//
// Add it with:   omarchy bar move io.github.sulaimanbaeisa.kumquat --section right
// Change the icon with an inline setting on its entry in ~/.config/omarchy/shell.json:
//   { "id": "io.github.sulaimanbaeisa.kumquat", "icon": "" }
import QtQuick
import Quickshell
import qs.Ui
import "Launch.js" as Launch

BarWidget {
  id: root
  moduleName: Launch.pluginId()

  readonly property string launcher: Launch.urlToPath(Qt.resolvedUrl("bin/kumquat"))

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function openKumquat() {
    if (launcher === "") {
      console.warn("[kumquat] cannot locate bin/kumquat from " + Qt.resolvedUrl("bin/kumquat"))
      return
    }
    Quickshell.execDetached(Launch.launchCommand(launcher, null))
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: String(root.setting("icon", "🍊"))
    tooltipText: "Kumquat: convert files"
    onPressed: function(buttonCode) {
      root.openKumquat()
    }
  }
}

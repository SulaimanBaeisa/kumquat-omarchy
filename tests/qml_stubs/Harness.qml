import QtQuick
import Quickshell

// Loads the plugin's real entry points inside a Qt QML engine and lets
// tests/test_plugin_qml.py drive them through plain properties:
// set `action`/`argument`, then read `response` (a JSON string).
Item {
  id: root

  property url pluginUrl
  property string action: ""
  property string argument: ""
  property string response: ""

  property var overlay: null
  property var widget: null

  QtObject {
    id: shellStub
    property var hidden: []
    function hide(id) { hidden = hidden.concat([id]) }
  }

  function load(name, properties) {
    const component = Qt.createComponent(pluginUrl + "/" + name)
    if (component.status !== Component.Ready)
      throw new Error(component.errorString())
    const item = component.createObject(root, properties)
    if (item === null)
      throw new Error("could not create " + name)
    return item
  }

  function snapshot() {
    return JSON.stringify({
      calls: Quickshell.calls,
      hidden: shellStub.hidden,
      opened: root.overlay ? root.overlay.opened : null,
      widget: root.widget ? {
        moduleName: root.widget.moduleName,
        text: root.widget.children[0].text,
        tooltip: root.widget.children[0].tooltipText,
      } : null,
    })
  }

  onActionChanged: {
    if (action === "")
      return
    try {
      if (action === "snapshot")
        response = snapshot()
      else if (action === "overlay.create")
        overlay = load("Overlay.qml", { shell: shellStub, manifest: JSON.parse(argument) })
      else if (action === "overlay.create-bare")
        overlay = load("Overlay.qml", {})
      else if (action === "overlay.open")
        overlay.open(argument === "<undefined>" ? undefined : argument)
      else if (action === "overlay.close")
        overlay.close()
      else if (action === "widget.create")
        widget = load("BarWidget.qml", { settings: JSON.parse(argument) })
      else if (action === "widget.press")
        widget.children[0].pressed(parseInt(argument))
      else
        throw new Error("unknown action " + action)
      if (action !== "snapshot")
        response = snapshot()
    } catch (error) {
      response = JSON.stringify({ error: String(error) })
    }
  }
}

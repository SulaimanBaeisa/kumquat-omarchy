import QtQuick

// Mirrors shell/Ui/BarWidget.qml: host-supplied `bar`, `moduleName`, `settings`.
Item {
  id: root
  property QtObject bar: null
  property string moduleName: ""
  property var settings: ({})
  property string fixedEdge: "center"
  readonly property bool vertical: bar ? bar.vertical : false

  function setting(name, fallback) {
    var value = settings[name]
    return value === undefined || value === null ? fallback : value
  }
}

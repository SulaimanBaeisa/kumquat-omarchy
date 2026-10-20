import QtQuick

// Mirrors the public surface of shell/Ui/WidgetButton.qml that plugins use.
Item {
  id: root
  property QtObject bar: null
  property string text: ""
  property string tooltipText: ""
  signal pressed(int button)
  implicitWidth: 24
  implicitHeight: 24
}

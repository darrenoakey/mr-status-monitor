import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15

Window {
    id: window
    width: 850
    height: 300
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    color: "transparent"
    visible: true
    
    Material.theme: Material.Light
    Material.accent: Material.Blue
    
    property bool isDragging: false
    property point dragStart: Qt.point(0, 0)
    
    Rectangle {
        id: mainCard
        anchors.fill: parent
        anchors.margins: 4
        radius: 8
        color: Material.backgroundColor
        
        border.color: Material.color(Material.Grey, Material.Shade300)
        border.width: 1
        
        // Drop shadow effect
        Rectangle {
            anchors.fill: parent
            anchors.topMargin: 2
            anchors.leftMargin: 2
            radius: parent.radius
            color: "#20000000"
            z: -1
        }
        
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 0
            spacing: 0
            
            // Title bar
            Rectangle {
                id: titleBar
                Layout.fillWidth: true
                Layout.preferredHeight: 48
                radius: 8
                color: Material.color(Material.Blue)
                
                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    height: parent.radius
                    color: parent.color
                }
                
                MouseArea {
                    id: titleMouseArea
                    anchors.fill: parent
                    
                    onPressed: {
                        window.isDragging = true
                        window.dragStart = Qt.point(mouseX, mouseY)
                    }
                    
                    onPositionChanged: {
                        if (window.isDragging) {
                            var deltaX = mouseX - window.dragStart.x
                            var deltaY = mouseY - window.dragStart.y
                            window.x += deltaX
                            window.y += deltaY
                        }
                    }
                    
                    onReleased: {
                        window.isDragging = false
                    }
                }
                
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 8
                    
                    Label {
                        text: "MR Status Monitor"
                        font.pixelSize: 16
                        font.weight: Font.Medium
                        color: "white"
                        Layout.fillWidth: true
                    }
                    
                    Button {
                        text: "×"
                        font.pixelSize: 18
                        font.weight: Font.Bold
                        Material.background: Material.Red
                        Material.foreground: "white"
                        Layout.preferredWidth: 32
                        Layout.preferredHeight: 32
                        
                        onClicked: Qt.quit()
                    }
                }
            }
            
            // Header row
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 40
                color: Material.color(Material.Grey, Material.Shade50)
                
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 16
                    spacing: 0
                    
                    Label {
                        text: "Repo"
                        font.weight: Font.Medium
                        Layout.preferredWidth: 60
                        color: Material.color(Material.Grey, Material.Shade700)
                    }
                    
                    Label {
                        text: "MR#"
                        font.weight: Font.Medium
                        Layout.preferredWidth: 50
                        color: Material.color(Material.Grey, Material.Shade700)
                    }
                    
                    Label {
                        text: "Branch"
                        font.weight: Font.Medium
                        Layout.preferredWidth: 120
                        color: Material.color(Material.Grey, Material.Shade700)
                    }
                    
                    Label {
                        text: "Title"
                        font.weight: Font.Medium
                        Layout.fillWidth: true
                        color: Material.color(Material.Grey, Material.Shade700)
                    }
                    
                    Label {
                        text: "Status"
                        font.weight: Font.Medium
                        Layout.preferredWidth: 320  // Fixed width for ~4 pills
                        horizontalAlignment: Text.AlignLeft
                        color: Material.color(Material.Grey, Material.Shade700)
                    }
                }
                
                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    height: 1
                    color: Material.color(Material.Grey, Material.Shade300)
                }
            }
            
            // Content area
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true
                
                // Loading indicator
                Rectangle {
                    id: loadingArea
                    anchors.fill: parent
                    color: "white"
                    visible: controller ? controller.loading : false
                    
                    ColumnLayout {
                        anchors.centerIn: parent
                        spacing: 16
                        
                        BusyIndicator {
                            Layout.alignment: Qt.AlignHCenter
                            running: controller ? controller.loading : false
                        }
                        
                        Label {
                            text: "Loading merge requests..."
                            Layout.alignment: Qt.AlignHCenter
                            font.pixelSize: 14
                            color: Material.color(Material.Grey, Material.Shade600)
                        }
                    }
                }
                
                // MR List
                ScrollView {
                    anchors.fill: parent
                    visible: controller ? !controller.loading : true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    ScrollBar.vertical.policy: ScrollBar.AsNeeded
                    
                    ListView {
                        id: listView
                        model: controller ? controller.model : null
                        
                        delegate: Rectangle {
                            id: itemRect
                            width: listView.width
                            height: 48
                            color: index % 2 === 0 ? "white" : Material.color(Material.Grey, Material.Shade50)
                            
                            
                            MouseArea {
                                anchors.fill: parent
                                acceptedButtons: Qt.LeftButton | Qt.RightButton

                                onClicked: {
                                    if (mouse.button === Qt.LeftButton) {
                                        controller.openUrl(model.mrUrl)
                                    }
                                }

                                onPressed: {
                                    if (mouse.button === Qt.RightButton) {
                                        contextMenu.mrUrl = model.mrUrl
                                        contextMenu.repo = model.repo
                                        contextMenu.mrNumber = model.mr
                                        contextMenu.popup()
                                    }
                                }

                                Menu {
                                    id: contextMenu
                                    property string mrUrl: ""
                                    property string repo: ""
                                    property string mrNumber: ""

                                    MenuItem {
                                        text: "Fix MR (Open Terminal)"
                                        onTriggered: {
                                            controller.launchFixMR(contextMenu.mrUrl)
                                        }
                                    }

                                    MenuSeparator { }

                                    MenuItem {
                                        text: "Open in Browser"
                                        onTriggered: {
                                            controller.openUrl(contextMenu.mrUrl)
                                        }
                                    }

                                    MenuItem {
                                        text: "Copy MR URL"
                                        onTriggered: {
                                            controller.copyToClipboard(contextMenu.mrUrl)
                                        }
                                    }
                                }
                            }
                            
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 16
                                anchors.rightMargin: 16
                                spacing: 0
                                
                                // Repo
                                Label {
                                    text: model.repo
                                    Layout.preferredWidth: 60
                                    font.pixelSize: 12
                                    font.weight: Font.Medium
                                    color: Material.color(Material.Blue)
                                    elide: Text.ElideRight
                                }
                                
                                // MR#
                                Label {
                                    text: model.mr
                                    Layout.preferredWidth: 50
                                    font.pixelSize: 12
                                    font.weight: Font.Medium
                                    color: Material.color(Material.Blue)
                                }
                                
                                // Branch
                                Label {
                                    id: branchLabel
                                    text: model.branch
                                    Layout.preferredWidth: 120
                                    font.pixelSize: 12
                                    elide: Text.ElideRight
                                    color: Material.color(Material.Grey, Material.Shade800)

                                    MouseArea {
                                        anchors.fill: parent
                                        acceptedButtons: Qt.RightButton

                                        onPressed: {
                                            if (mouse.button === Qt.RightButton) {
                                                branchContextMenu.branchName = model.branch
                                                branchContextMenu.repoName = model.repo
                                                branchContextMenu.popup()
                                            }
                                        }

                                        Menu {
                                            id: branchContextMenu
                                            property string branchName: ""
                                            property string repoName: ""

                                            MenuItem {
                                                text: "Copy Branch Name"
                                                onTriggered: {
                                                    controller.copyToClipboard(branchContextMenu.branchName)
                                                }
                                            }

                                            MenuSeparator { }

                                            MenuItem {
                                                text: "Checkout Branch"
                                                onTriggered: {
                                                    controller.checkoutBranch(branchContextMenu.repoName, branchContextMenu.branchName)
                                                }
                                            }
                                        }
                                    }
                                }
                                
                                // Title (flexible - grows/shrinks with window)
                                Label {
                                    text: model.title
                                    Layout.fillWidth: true
                                    font.pixelSize: 12
                                    elide: Text.ElideRight
                                    color: Material.color(Material.Grey, Material.Shade800)
                                }
                                
                                // Status Pills (fixed width)
                                Item {
                                    Layout.preferredWidth: 320
                                    Layout.preferredHeight: 24
                                    Layout.alignment: Qt.AlignVCenter

                                    Flow {
                                        anchors.left: parent.left
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: parent.width
                                        spacing: 6

                                        Repeater {
                                            model: statusPills.slice(0, 4)

                                            Rectangle {
                                                width: Math.max(70, pillLabel.contentWidth + 20)
                                                height: 24
                                                radius: 12
                                                color: modelData.color

                                                MouseArea {
                                                    anchors.fill: parent
                                                    enabled: modelData.url !== ""
                                                    onClicked: {
                                                        if (modelData.url) {
                                                            controller.openUrl(modelData.url)
                                                        }
                                                    }
                                                }

                                                Label {
                                                    id: pillLabel
                                                    anchors.centerIn: parent
                                                    text: modelData.text
                                                    color: "white"
                                                    font.pixelSize: 10
                                                    font.weight: Font.Medium
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            
                            // Bottom border
                            Rectangle {
                                anchors.bottom: parent.bottom
                                anchors.left: parent.left
                                anchors.right: parent.right
                                height: 1
                                color: Material.color(Material.Grey, Material.Shade200)
                            }
                        }
                        
                        // Empty state when no loading and no items
                        Rectangle {
                            anchors.fill: parent
                            visible: controller ? (!controller.loading && listView.count === 0) : (listView.count === 0)
                            color: "white"
                            
                            Label {
                                anchors.centerIn: parent
                                text: "No open merge requests"
                                font.pixelSize: 14
                                color: Material.color(Material.Grey, Material.Shade600)
                            }
                        }
                    }
                }
            }
            
            // Status bar
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 32
                color: Material.color(Material.Grey, Material.Shade50)
                radius: 8
                
                Rectangle {
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.right: parent.right
                    height: parent.radius
                    color: parent.color
                }
                
                Label {
                    id: statusLabel
                    anchors.centerIn: parent
                    text: "Initializing..."
                    font.pixelSize: 11
                    color: Material.color(Material.Grey, Material.Shade600)
                    
                    Connections {
                        target: controller
                        function onStatusChanged(status) {
                            statusLabel.text = status
                        }
                    }
                }
            }
        }
    }
}
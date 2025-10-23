#!/usr/bin/env python3

import sys
import signal
import logging
import multiprocessing
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
from PySide6.QtQuickControls2 import QQuickStyle

from .mr_model import MRModel
from .mr_status_controller import MRStatusController

logger = logging.getLogger(__name__)

# ##################################################################
# setup logging
# configures application logging to file in output directory
def setup_logging() -> None:
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    log_file = output_dir / "mr_status_monitor.log"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ])

# ##################################################################
# main entry point
# initializes qt application, loads qml ui, and starts event loop
def main() -> int:
    setup_logging()

    multiprocessing.set_start_method('spawn', force=True)

    QQuickStyle.setStyle("Material")

    app = QGuiApplication(sys.argv)

    controller = MRStatusController()

    def signal_handler(signum: int, frame: any) -> None:
        logger.info(f"received signal num={signum}")
        controller.cleanup()
        app.quit()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGQUIT, signal_handler)

    engine = QQmlApplicationEngine()
    qmlRegisterType(MRModel, "MRStatusBar", 1, 0, "MRModel")
    engine.rootContext().setContextProperty("controller", controller)

    qml_file = Path(__file__).parent.parent / "resources" / "mr-status-bar.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))

    if not engine.rootObjects():
        logger.error("failed to load qml file")
        return -1

    controller.load_config()
    controller.initialize_data()

    result = app.exec()

    controller.cleanup()

    return result

# ##################################################################
#
# standard python pattern for dispatching main
if __name__ == '__main__':
    sys.exit(main())

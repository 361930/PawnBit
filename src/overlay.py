import math
import sys
import threading
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QGuiApplication, QPolygon
from PyQt6.QtWidgets import QApplication, QWidget


class OverlayScreen(QWidget):
    def __init__(self, stockfish_queue):
        super().__init__()
        self.stockfish_queue = stockfish_queue

        # Set the window to be the size of the screen
        self.screen = QGuiApplication.screens()[0]
        self.setFixedWidth(self.screen.size().width())
        self.setFixedHeight(self.screen.size().height())

        # Set the window to be transparent
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)

        # A list of QPolygon objects containing the points of the arrows
        self.moves_to_draw = []
        self.arrow_colors = [
            QColor(0, 255, 0, 122),   # Best move: green
            QColor(0, 0, 255, 122),   # Second best: blue
            QColor(255, 255, 0, 122), # Third best: yellow
            QColor(255, 0, 0, 122)    # Default/fallback: red
        ]

        # Start the message queue thread
        self.message_queue_thread = threading.Thread(target=self.message_queue_thread)
        self.message_queue_thread.start()

    def message_queue_thread(self):
        """
        This thread is used to receive messages from the stockfish message queue
        and update the arrows
        Args:
            None
        Returns:
            None
        """

        while True:
            message = self.stockfish_queue.get()
            self.set_arrows(message)

    def set_arrows(self, moves_data):
        """
        This function is used to set the arrows to be drawn on the screen
        Args:
            moves_data: A list of dictionaries with move coordinates and rank
        Returns:
            None
        """

        self.moves_to_draw = []
        if isinstance(moves_data, list):
            for move_info in moves_data:
                start_coords = move_info.get('coords', [[0,0]])[0]
                end_coords = move_info.get('coords', [[0,0]])[1]
                start_point = QPoint(start_coords[0], start_coords[1])
                end_point = QPoint(end_coords[0], end_coords[1])
                poly = self.get_arrow_polygon(start_point, end_point)
                rank = move_info.get('rank', 3)
                color = self.arrow_colors[min(rank, len(self.arrow_colors) - 1)]
                self.moves_to_draw.append({'polygon': poly, 'color': color})
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        for move in self.moves_to_draw:
            painter.setPen(QPen(Qt.GlobalColor.black, 1, Qt.PenStyle.NoPen))
            painter.setBrush(QBrush(move['color'], Qt.BrushStyle.SolidPattern))
            painter.drawPolygon(move['polygon'])
        painter.end()

    def get_arrow_polygon(self, start_point, end_point):
        """
        This function is used to get the polygon for the arrow
        Args:
            start_point: The start point of the arrow
            end_point: The end point of the arrow
        Returns:
            A QPolygon object containing the points of the arrow
        """

        try:
            dx, dy = start_point.x() - end_point.x(), start_point.y() - end_point.y()

            # Normalize the vector
            leng = math.sqrt(dx ** 2 + dy ** 2)
            norm_x, norm_y = dx / leng, dy / leng

            # Get the perpendicular vector
            perp_x = -norm_y
            perp_y = norm_x

            arrow_height = 25
            left_x = end_point.x() + arrow_height * norm_x * 1.5 + arrow_height * perp_x
            left_y = end_point.y() + arrow_height * norm_y * 1.5 + arrow_height * perp_y

            right_x = end_point.x() + arrow_height * norm_x * 1.5 - arrow_height * perp_x
            right_y = end_point.y() + arrow_height * norm_y * 1.5 - arrow_height * perp_y

            point2 = QPoint(int(left_x), int(left_y))
            point3 = QPoint(int(right_x), int(right_y))

            mid_point1 = QPoint(int((2 / 5) * point2.x() + (3 / 5) * point3.x()), int((2 / 5) * point2.y() + (3 / 5) * point3.y()))
            mid_point2 = QPoint(int((3 / 5) * point2.x() + (2 / 5) * point3.x()), int((3 / 5) * point2.y() + (2 / 5) * point3.y()))

            start_left = QPoint(int(start_point.x() + (arrow_height / 5) * perp_x), int(start_point.y() + (arrow_height / 5) * perp_y))
            start_right = QPoint(int(start_point.x() - (arrow_height / 5) * perp_x), int(start_point.y() - (arrow_height / 5) * perp_y))

            return QPolygon([end_point, point2, mid_point1, start_right, start_left, mid_point2, point3])
        except Exception as e:
            print(e)
            return QPolygon()


def run(stockfish_queue):
    """
    This function is used to run the overlay
    Args:
        stockfish_queue: The message queue used to communicate with the stockfish thread
    Returns:
        None
    """

    app = QApplication(sys.argv)
    overlay = OverlayScreen(stockfish_queue)
    overlay.show()
    app.exec()

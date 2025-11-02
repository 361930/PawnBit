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
                square_size = move_info.get('square_size', 50)
                start_point = QPoint(start_coords[0], start_coords[1])
                end_point = QPoint(end_coords[0], end_coords[1])
                poly = self.get_arrow_polygon(start_point, end_point, square_size)
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

    def get_arrow_polygon(self, start_point, end_point, square_size=50):
        """
        This function is used to get the polygon for the arrow
        Args:
            start_point: The start point of the arrow
            end_point: The end point of the arrow
            square_size: The size of a square on the chessboard, for scaling.
        Returns:
            A QPolygon object containing the points of the arrow
        """
        try:
            # Scale arrow dimensions based on square size for better visuals
            head_width = square_size * 0.45
            head_length = square_size * 0.45
            shaft_width = head_width / 2.5

            dx = end_point.x() - start_point.x()
            dy = end_point.y() - start_point.y()
            length = math.sqrt(dx * dx + dy * dy)

            if length < head_length: # If arrow is too short, don't draw
                return QPolygon()

            # Normalize the main vector (from start to end)
            udx, udy = dx / length, dy / length

            # Perpendicular vector
            pdx, pdy = -udy, udx

            # Point where the shaft meets the head
            neck_point = QPoint(
                int(end_point.x() - head_length * udx),
                int(end_point.y() - head_length * udy)
            )

            # Tip of the arrow
            p1 = end_point

            # Arrowhead base points (wide part)
            p2 = QPoint(
                int(neck_point.x() + head_width / 2 * pdx),
                int(neck_point.y() + head_width / 2 * pdy)
            )
            p3 = QPoint(
                int(neck_point.x() - head_width / 2 * pdx),
                int(neck_point.y() - head_width / 2 * pdy)
            )

            # Shaft points at the neck
            p4 = QPoint(
                int(neck_point.x() + shaft_width / 2 * pdx),
                int(neck_point.y() + shaft_width / 2 * pdy)
            )
            p5 = QPoint(
                int(neck_point.x() - shaft_width / 2 * pdx),
                int(neck_point.y() - shaft_width / 2 * pdy)
            )

            # Shaft points at the start
            p6 = QPoint(
                int(start_point.x() + shaft_width / 2 * pdx),
                int(start_point.y() + shaft_width / 2 * pdy)
            )
            p7 = QPoint(
                int(start_point.x() - shaft_width / 2 * pdx),
                int(start_point.y() - shaft_width / 2 * pdy)
            )

            return QPolygon([p1, p2, p4, p6, p7, p5, p3])

        except (ZeroDivisionError, Exception) as e:
            print(f"Error calculating arrow polygon: {e}")
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

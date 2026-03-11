

# ==========================================================
# IMPORTS
# ==========================================================

import pygame
import sys
import serial
import threading
import time


# ==========================================================
# INITIALIZATION
# ==========================================================

pygame.init()


# ==========================================================
# GAME CONSTANTS
# ==========================================================

BOARD_SIZE = 4
SQUARE_SIZE = 150
WINDOW_SIZE = BOARD_SIZE * SQUARE_SIZE

WHITE = (255, 255, 255)
LIGHT_GRAY = (220, 220, 220)
BLACK = (0, 0, 0)

HIGHLIGHT_COLOR = (173, 216, 230)
POSSIBLE_MOVE_COLOR = (144, 238, 144)
CAPTURE_MOVE_COLOR = (255, 0, 0)

LABEL_FONT_SIZE = 14
LABEL_BG_PADDING = 6


# ==========================================================
# UID TO PIECE MAPPING
# ==========================================================

UID_TO_PIECE = {

    "C5B7BD01": ("White", "rook"),
    "F3C7B501": ("White", "king"),
    "9B850802": ("White", "knight"),
    "7A74B701": ("White", "pawn"),

    "AB980802": ("Black", "rook"),
    "5BCA0E02": ("Black", "king"),
    "1BFD0802": ("Black", "knight"),
    "CE890E02": ("Black", "pawn"),
}


# ==========================================================
# EXPECTED START POSITIONS
# ==========================================================

EXPECTED = {

    ("White","rook"): (3,0),
    ("White","king"): (3,1),
    ("White","knight"): (3,2),
    ("White","pawn"): (3,3),

    ("Black","rook"): (0,0),
    ("Black","king"): (0,1),
    ("Black","knight"): (0,2),
    ("Black","pawn"): (0,3),
}


# ==========================================================
# DISPLAY SETUP
# ==========================================================

screen = pygame.display.set_mode((WINDOW_SIZE, WINDOW_SIZE))
pygame.display.set_caption("Smart Chessboard")


piece_images = {}
show_rules = False

rules_font = pygame.font.SysFont("Arial",18)

rules_txt = [

    "Simplified Rules:",
    "- Rook: Up to 2 squares straight",
    "- Knight: 1 square diagonally",
    "- King: 1 square any direction",
    "- Pawn: 1 forward or diagonal capture"
]


# ==========================================================
# LED FEEDBACK COMMUNICATION
# ==========================================================

def send_led_feedback(comm, type_, square=None):

    """
    Sends LED highlight or feedback commands to the Arduino.
    """

    if not comm or not hasattr(comm, 'send_feedback'):
        return

    if type_ == "clear":
        comm.send_feedback("highlight clear")

    elif type_ in ("selected", "move", "capture"):
        comm.send_feedback(f"highlight {type_} {square}")

    elif type_ in ("invalid_move", "blink_piece", "expected"):
        comm.send_feedback(f"feedback {type_} {square}")


# ==========================================================
# CHESS PIECE CLASS
# ==========================================================

class ChessPiece:

    """
    Represents a chess piece and its movement logic
    """

    def __init__(self, color, piece_type, position, uid):

        self.color = color
        self.piece_type = piece_type
        self.position = position
        self.uid = uid


    def get_possible_moves(self, board):

        """
        Calculate valid moves for the piece
        """

        row, col = self.position
        moves = []

        # Pawn movement

        if self.piece_type == "pawn":

            direction = -1 if self.color == "White" else 1
            next_row = row + direction

            if 0 <= next_row < BOARD_SIZE:

                if board[next_row][col] is None:
                    moves.append((next_row, col))

                for dc in (-1, 1):

                    nc = col + dc

                    if 0 <= nc < BOARD_SIZE:

                        target = board[next_row][nc]

                        if target and target.color != self.color:
                            moves.append((next_row, nc))


        # King movement

        elif self.piece_type == "king":

            for dr in [-1,0,1]:
                for dc in [-1,0,1]:

                    if dr == 0 and dc == 0:
                        continue

                    nr = row + dr
                    nc = col + dc

                    if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:

                        if board[nr][nc] is None or board[nr][nc].color != self.color:
                            moves.append((nr,nc))


        # Knight movement (simplified)

        elif self.piece_type == "knight":

            for dr,dc in [(-1,-1),(-1,1),(1,-1),(1,1)]:

                nr = row + dr
                nc = col + dc

                if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:

                    if board[nr][nc] is None or board[nr][nc].color != self.color:
                        moves.append((nr,nc))


        # Rook movement

        elif self.piece_type == "rook":

            for c in range(col-1,-1,-1):

                if board[row][c] is None:
                    moves.append((row,c))

                elif board[row][c].color != self.color:
                    moves.append((row,c))
                    break
                else:
                    break


            for c in range(col+1,BOARD_SIZE):

                if board[row][c] is None:
                    moves.append((row,c))

                elif board[row][c].color != self.color:
                    moves.append((row,c))
                    break
                else:
                    break


        return moves


# ==========================================================
# CHESS BOARD CLASS
# ==========================================================

class ChessBoard:

    """
    Manages the board state and rendering
    """

    def __init__(self, serial_comm=None):

        self.board = [[None]*BOARD_SIZE for _ in range(BOARD_SIZE)]

        self.selected_piece = None
        self.possible_moves = []

        self.piece_by_uid = {}

        self.serial_comm = serial_comm

        self.load_images()


    def setup_board(self):

        """
        Initialize pieces on the board
        """

        self.board = [[None]*BOARD_SIZE for _ in range(BOARD_SIZE)]
        self.piece_by_uid = {}

        for uid,(color,ptype) in UID_TO_PIECE.items():

            r,c = EXPECTED[(color,ptype)]

            piece = ChessPiece(color,ptype,(r,c),uid)

            self.board[r][c] = piece
            self.piece_by_uid[uid] = piece


    def load_images(self):

        """
        Create graphical piece representations
        """

        for color in ["White","Black"]:

            for ptype,label in [("pawn","P"),("knight","N"),("king","K"),("rook","R")]:

                surf = pygame.Surface((SQUARE_SIZE-20,SQUARE_SIZE-20),pygame.SRCALPHA)

                bg = (240,240,240) if color == "White" else (50,50,50)

                pygame.draw.circle(surf,bg,(SQUARE_SIZE//2-10,SQUARE_SIZE//2-10),SQUARE_SIZE//2-15)

                font = pygame.font.SysFont("Arial",20)

                txt = font.render(label,True,BLACK if color=="White" else WHITE)

                surf.blit(txt,txt.get_rect(center=(SQUARE_SIZE//2-10,SQUARE_SIZE//2-10)))

                piece_images[(color,ptype)] = surf


# ==========================================================
# SERIAL COMMUNICATION
# ==========================================================

class SerialCommunication(threading.Thread):

    """
    Handles serial communication with the Arduino
    """

    def __init__(self, board, port='COM3', baudrate=115200):

        super().__init__()

        self.board = board
        self.port = port
        self.baudrate = baudrate

        self.running = True
        self.serial_connection = None

        self.daemon = True

        try:

            self.serial_connection = serial.Serial(self.port,self.baudrate,timeout=1)

            print(f"Serial connection established on {self.port}")

        except serial.SerialException as e:

            print(f"Could not open serial port {self.port}: {e}")
            self.running = False


# ==========================================================
# MAIN GAME LOOP
# ==========================================================

def main():

    serial_comm = SerialCommunication(None)

    board = ChessBoard(serial_comm)

    serial_comm.board = board

    board.setup_board()

    if serial_comm.running:
        serial_comm.start()

    running = True

    while running:

        for event in pygame.event.get():

            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.MOUSEBUTTONDOWN:

                if event.button == 1:
                    board.handle_click(event.pos)


        screen.fill(BLACK)

        board.draw()

        pygame.display.flip()

        time.sleep(0.01)


    if serial_comm.running:
        serial_comm.stop()

    pygame.quit()
    sys.exit()


# ==========================================================
# PROGRAM ENTRY POINT
# ==========================================================

if __name__ == "__main__":
    main()

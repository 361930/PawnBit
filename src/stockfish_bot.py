import multiprocess
from stockfish import Stockfish
import pyautogui
import time
import sys
import os
import chess
import re
from collections import defaultdict
from grabbers.chesscom_grabber import ChesscomGrabber
from grabbers.lichess_grabber import LichessGrabber
from utilities import char_to_num, attach_to_session
import keyboard


class StockfishBot(multiprocess.Process):
    def __init__(self, chrome_url, chrome_session_id, website, pipe, overlay_queue, stockfish_path, enable_manual_mode, enable_mouseless_mode, enable_non_stop_puzzles, enable_non_stop_matches, mouse_latency, bongcloud, slow_mover, skill_level, stockfish_depth, memory, cpu_threads):
        multiprocess.Process.__init__(self)

        self.chrome_url = chrome_url
        self.chrome_session_id = chrome_session_id
        self.website = website
        self.pipe = pipe
        self.overlay_queue = overlay_queue
        self.stockfish_path = stockfish_path
        self.enable_manual_mode = enable_manual_mode
        self.enable_mouseless_mode = enable_mouseless_mode
        self.enable_non_stop_puzzles = enable_non_stop_puzzles
        self.enable_non_stop_matches = enable_non_stop_matches
        self.mouse_latency = mouse_latency
        self.bongcloud = bongcloud
        self.slow_mover = slow_mover
        self.skill_level = skill_level
        self.stockfish_depth = stockfish_depth
        self.grabber = None
        self.memory = memory
        self.cpu_threads = cpu_threads
        self.is_white = None
        self.driver = None # Driver for this process
        # Removed self.move_counts

    # Converts a move to screen coordinates
    # Example: "a1" -> (x, y)
    def move_to_screen_pos(self, move):
        # Get the web element of the board
        board_elem = self.grabber.get_board()

        # Get the absolute top left corner of the website's viewport using JavaScript
        canvas_x_offset = self.driver.execute_script("return window.screenX + (window.outerWidth - window.innerWidth) / 2")
        canvas_y_offset = self.driver.execute_script("return window.screenY + window.outerHeight - window.innerHeight")

        # Get the absolute board position on the screen
        board_x = canvas_x_offset + board_elem.location["x"]
        board_y = canvas_y_offset + board_elem.location["y"]

        # Get the size of a single square
        square_size = board_elem.size['width'] / 8

        # Depending on the player color, the board is flipped, so the coordinates need to be adjusted
        if self.is_white:
            x = board_x + square_size * (char_to_num(move[0]) - 1) + square_size / 2
            y = board_y + square_size * (8 - int(move[1])) + square_size / 2
        else:
            x = board_x + square_size * (8 - char_to_num(move[0])) + square_size / 2
            y = board_y + square_size * (int(move[1]) - 1) + square_size / 2

        return x, y

    def get_move_pos(self, move):  # sourcery skip: remove-redundant-slice-index
        # Get the start and end position screen coordinates
        start_pos_x, start_pos_y = self.move_to_screen_pos(move[0:2])
        end_pos_x, end_pos_y = self.move_to_screen_pos(move[2:4])

        return (start_pos_x, start_pos_y), (end_pos_x, end_pos_y)


    def make_move(self, move):  # sourcery skip: extract-method
        # Get the start and end position screen coordinates
        start_pos, end_pos = self.get_move_pos(move)

        # Drag the piece from the start to the end position
        pyautogui.moveTo(start_pos[0], start_pos[1])
        time.sleep(self.mouse_latency)
        pyautogui.dragTo(end_pos[0], end_pos[1])

        # Check for promotion. If there is a promotion,
        # promote to the corresponding piece type
        if len(move) == 5:
            time.sleep(0.1)
            end_pos_x = None
            end_pos_y = None
            if move[4] == "n":
                end_pos_x, end_pos_y = self.move_to_screen_pos(move[2] + str(int(move[3]) - 1))
            elif move[4] == "r":
                end_pos_x, end_pos_y = self.move_to_screen_pos(move[2] + str(int(move[3]) - 2))
            elif move[4] == "b":
                end_pos_x, end_pos_y = self.move_to_screen_pos(move[2] + str(int(move[3]) - 3))

            pyautogui.moveTo(x=end_pos_x, y=end_pos_y)
            pyautogui.click(button='left')

    def wait_for_gui_to_delete(self):
        while self.pipe.recv() != "DELETE":
            pass

    def go_to_next_puzzle(self):
        self.grabber.click_puzzle_next()
        self.pipe.send("RESTART")
        self.wait_for_gui_to_delete()

    def find_new_online_match(self):
        time.sleep(2)
        self.grabber.click_game_next()
        self.pipe.send("RESTART")
        self.wait_for_gui_to_delete()
    
    def send_evaluation(self, stockfish):
        try:
            evaluation = stockfish.get_evaluation()
            self.pipe.send({'type': 'EVAL', 'data': evaluation})
        except Exception as e:
            print(f"Error sending evaluation: {e}")

    # Removed classify_move

    def run(self):
        # sourcery skip: extract-duplicate-method, switch, use-fstring-for-concatenation
        if self.website == "chesscom":
            self.grabber = ChesscomGrabber(self.chrome_url, self.chrome_session_id)
        else:
            self.grabber = LichessGrabber(self.chrome_url, self.chrome_session_id)

        # Attach to the browser session to get window coordinates and execute scripts
        self.driver = attach_to_session(self.chrome_url, self.chrome_session_id)

        # Initialize Stockfish
        parameters = {
            "Threads": self.cpu_threads,
            "Hash": self.memory,
            "Ponder": "true",
            "Slow Mover": self.slow_mover,
            "Skill Level": self.skill_level
        }
        try:
            stockfish = Stockfish(path=self.stockfish_path, depth=self.stockfish_depth, parameters=parameters)
        except PermissionError:
            self.pipe.send("ERR_PERM")
            return
        except OSError:
            self.pipe.send("ERR_EXE")
            return

        try:
            # Return if the board element is not found
            self.grabber.update_board_elem()
            if self.grabber.get_board() is None:
                self.pipe.send("ERR_BOARD")
                return

            square_size = self.grabber.get_board().size['width'] / 8

            # Find out what color the player has
            self.is_white = self.grabber.is_white()
            if self.is_white is None:
                self.pipe.send("ERR_COLOR")
                return
            
            self.pipe.send({'type': 'PLAYER_COLOR', 'data': self.is_white})

            # Get the starting position
            # Return if the starting position is not found
            move_list = self.grabber.get_move_list()
            if move_list is None:
                self.pipe.send("ERR_MOVES")
                return

            # Check if the game is over
            score_pattern = r"([0-9]+)\-([0-9]+)"
            if len(move_list) > 0 and re.match(score_pattern, move_list[-1]):
                self.pipe.send("ERR_GAMEOVER")
                return

            # Update the board with the starting position
            board = chess.Board()
            for move in move_list:
                board.push_san(move)
            move_list_uci = [move.uci() for move in board.move_stack]

            # Update Stockfish with the starting position
            stockfish.set_position(move_list_uci)

            # Notify GUI that bot is ready
            self.pipe.send("START")

            # Send the first moves to the GUI (if there are any)
            if len(move_list) > 0:
                self.pipe.send("M_MOVE" + ",".join(move_list))

            self.send_evaluation(stockfish)

            # Start the game loop
            while True:
                # Act if it is the player's turn
                if (self.is_white and board.turn == chess.WHITE) or (not self.is_white and board.turn == chess.BLACK):
                    
                    # Removed eval_before and player_turn, no longer classifying
                    
                    # Think of a move to play
                    move = None
                    move_count = len(board.move_stack)
                    if self.bongcloud and move_count <= 3:
                        if move_count == 0:
                            move = "e2e3"
                        elif move_count == 1:
                            move = "e7e6"
                        elif move_count == 2:
                            move = "e1e2"
                        elif move_count == 3:
                            move = "e8e7"

                        # Hardcoded bongcloud move is not legal,
                        # so find a legal move
                        if not board.is_legal(chess.Move.from_uci(move)):
                            move = stockfish.get_best_move()
                    else:
                        if self.enable_manual_mode:
                            top_moves = stockfish.get_top_moves(3)
                            if top_moves:
                                move = top_moves[0]['Move']
                            else:
                                move = stockfish.get_best_move() # Fallback
                        else:
                            move = stockfish.get_best_move()


                    # Wait for keypress or player movement if in manual mode
                    self_moved = False
                    if self.enable_manual_mode:
                        if 'top_moves' in locals() and top_moves:
                            overlay_moves = []
                            gui_moves_data = [] # Renamed from gui_moves
                            current_move_number = board.fullmove_number
                            is_white_turn = board.turn == chess.WHITE
                            
                            # *** FIX ***
                            # Save the original FEN position to restore Stockfish later
                            original_fen = stockfish.get_fen_position()
                            
                            for i, move_info in enumerate(top_moves):
                                move_uci = move_info['Move']
                                start_pos, end_pos = self.get_move_pos(move_uci)
                                overlay_moves.append({
                                    'coords': ((int(start_pos[0]), int(start_pos[1])), (int(end_pos[0]), int(end_pos[1]))),
                                    'rank': i,
                                    'square_size': square_size
                                })
                                try:
                                    san_move = board.san(chess.Move.from_uci(move_uci))
                                except Exception:
                                    san_move = move_uci

                                if move_info['Mate'] is not None:
                                    mate_val = move_info['Mate']
                                    if board.turn == chess.BLACK:
                                        mate_val = -mate_val
                                    evaluation = f"M{mate_val}"
                                else:
                                    cp = move_info.get('Centipawn')
                                    if cp is not None:
                                        if board.turn == chess.BLACK:
                                            cp = -cp
                                        evaluation = f"{cp / 100.0:+.2f}"
                                    else:
                                        evaluation = "N/A"
                                
                                # --- Sequence Generation ---
                                sequence_moves_san = []
                                temp_board = board.copy()
                                
                                # 1. Add the first move
                                first_move_obj = chess.Move.from_uci(move_uci)
                                sequence_moves_san.append(temp_board.san(first_move_obj))
                                temp_board.push(first_move_obj)
                                
                                # Generate next 4 plys
                                for j in range(4): # 2 more full moves (4 plys)
                                    # *** FIX ***
                                    # Set stockfish's internal position to the temp board's FEN
                                    stockfish.set_fen_position(temp_board.fen())
                                    # Get the best move from stockfish's internal state
                                    next_move_uci = stockfish.get_best_move()
                                    
                                    if not next_move_uci:
                                        break
                                    
                                    try:
                                        next_move_obj = chess.Move.from_uci(next_move_uci)
                                        sequence_moves_san.append(temp_board.san(next_move_obj))
                                        temp_board.push(next_move_obj)
                                    except Exception as e:
                                        print(f"Error processing next move: {e}")
                                        break
                                
                                # --- Format the sequence string (NEW FORMAT - like Image 1) ---
                                seq_str = ""
                                max_white_len = 0
                                
                                # Determine max width for White's moves for alignment
                                for k, move_san_str in enumerate(sequence_moves_san):
                                    if (is_white_turn and k % 2 == 0) or (not is_white_turn and k % 2 != 0):
                                        # It's White's move
                                        max_white_len = max(max_white_len, len(move_san_str))
                                
                                move_num_counter = current_move_number
                                for k, move_san_str in enumerate(sequence_moves_san):
                                    is_white_move_in_seq = (is_white_turn and k % 2 == 0) or (not is_white_turn and k % 2 != 0)
                                    is_black_move_in_seq = (is_white_turn and k % 2 != 0) or (not is_white_turn and k % 2 == 0)

                                    if is_white_move_in_seq:
                                        if seq_str != "" and not seq_str.endswith('\n'): # Ensure newline before new move number
                                            seq_str += '\n'
                                        seq_str += f"{move_num_counter}. {move_san_str.ljust(max_white_len + 2)} " # Left-justify White's move
                                    elif is_black_move_in_seq:
                                        seq_str += f"{move_san_str}\n" # Black's move, followed by a newline
                                        
                                    if not is_white_move_in_seq: # Increment move number after Black's move (or if Black started)
                                        move_num_counter += 1

                                # If the sequence ends with White's move, add a final newline for consistency
                                if not seq_str.endswith('\n'):
                                    seq_str += '\n'


                                gui_moves_data.append({
                                    'move': san_move,
                                    'eval': evaluation,
                                    'sequence': seq_str.strip()
                                })
                                
                                # *** FIX ***
                                # Restore stockfish to the original position for the next iteration
                                stockfish.set_fen_position(original_fen)
                                
                            self.overlay_queue.put(overlay_moves)
                            self.pipe.send({'type': 'TOP_MOVES', 'data': gui_moves_data})
                        elif move:
                            move_start_pos, move_end_pos = self.get_move_pos(move)
                            self.overlay_queue.put([{'coords':((int(move_start_pos[0]), int(move_start_pos[1])), (int(move_end_pos[0]), int(move_end_pos[1]))), 'rank': 3, 'square_size': square_size}])
                        
                        if not move:
                            return

                        while True:
                            if keyboard.is_pressed("3"):
                                break

                            current_move_list = self.grabber.get_move_list()
                            if len(move_list) != len(current_move_list):
                                self_moved = True
                                move_list = current_move_list
                                move_san = move_list[-1]
                                move = board.parse_san(move_san).uci()
                                break
                            time.sleep(0.01)
                    
                    # Make the move on the board and update stockfish
                    move_san = board.san(chess.Move.from_uci(move))
                    board.push_uci(move)
                    stockfish.make_moves_from_current_position([move])

                    if not self_moved:
                        if self.enable_mouseless_mode and not self.grabber.is_game_puzzles():
                            self.grabber.make_mouseless_move(move, move_count + 1)
                        else:
                            self.make_move(move)
                    
                    # Removed eval_after, move_symbol, move_counts logic

                    self.overlay_queue.put([])
                    # The empty TOP_MOVES message was removed to prevent GUI flicker
                    # if self.enable_manual_mode:
                    #    self.pipe.send({'type': 'TOP_MOVES', 'data': []}) # <--- THIS LINE IS REMOVED

                    # Send the move to the GUI (simplified)
                    move_data = {'move': move_san}
                    self.pipe.send({'type': 'MOVE', 'data': move_data})
                    # Removed MOVE_COUNTS send
                    
                    self.send_evaluation(stockfish)

                    # Check if the game is over
                    if board.is_checkmate():
                        if self.enable_non_stop_puzzles and self.grabber.is_game_puzzles():
                            self.go_to_next_puzzle()
                        elif self.enable_non_stop_matches and not self.enable_non_stop_puzzles:
                            self.find_new_online_match()
                        return

                    time.sleep(0.1)

                # Wait for a response from the opponent
                previous_move_list = move_list.copy()
                # Removed eval_before, opponent_turn
                
                while True:
                    if self.grabber.is_game_over():
                        if self.enable_non_stop_puzzles and self.grabber.is_game_puzzles():
                            self.go_to_next_puzzle()
                        elif self.enable_non_stop_matches and not self.enable_non_stop_puzzles:
                            self.find_new_online_match()
                        return
                    move_list = self.grabber.get_move_list()
                    if move_list is None:
                        return
                    if len(move_list) > len(previous_move_list):
                        break

                # Get the move that the opponent made
                move = move_list[-1]
                board.push_san(move)
                stockfish.make_moves_from_current_position([str(board.peek())])
                # Removed eval_after, move_symbol, move_counts logic

                move_data = {'move': move}
                self.pipe.send({'type': 'MOVE', 'data': move_data})
                # Removed MOVE_COUNTS send
                self.send_evaluation(stockfish)

                if board.is_checkmate():
                    if self.enable_non_stop_puzzles and self.grabber.is_game_puzzles():
                        self.go_to_next_puzzle()
                    elif self.enable_non_stop_matches and not self.enable_non_stop_puzzles:
                        self.find_new_online_match()
                    return
        except Exception as e:
            print(f"An error occurred in stockfish_bot: {e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(exc_type, fname, exc_tb.tb_lineno)



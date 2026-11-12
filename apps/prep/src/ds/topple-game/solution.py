"""
Toppling board game — status checker.
 
Rules implemented (from the prompt):
  * Players alternate turns, player 1 goes first. A turn is:
      1. place a piece            ("pXY")
      2. optional topple          ("tXYD"), D in {l, r, u, d}
  * Place: an open square becomes owned by the mover (1 piece);
    placing on an already-owned square just grows that stack.
  * Topple (square must hold 2+ pieces): the whole stack is picked up,
    the square becomes open, and one piece is dropped on each successive
    square walking in direction D:
      - drop on an open square     -> toppling player owns it (1 piece)
      - drop on own square         -> that stack grows by 1
      - drop on opponent's square  -> the square is CAPTURED: the whole
                                      stack (its pieces + the dropped one)
                                      now belongs to the toppling player
      - pieces carried past the board edge are lost
  * The game ends when one player has no pieces left on the board;
    the other player wins.
 
Coordinate convention (the prompt leaves the axes open, so it is pinned
here and trivially changeable via the STEP table):
  (x, y) = (column, row), with (0, 0) the top-left square.
  l: x-1    r: x+1    u: y-1    d: y+1
"""

IN_PROGRESS = "in-progress"
P1_WINS = "player1 is the winner"
P2_WINS = "player2 is the winner"


def get_game_status(moves, size):
    """Run through `moves` on a size x size board and return the status.
 
    Args:
        moves: list of move strings — "pXY" places a piece on (x, y);
               "tXYD" topples the stack at (x, y) in direction D.
        size:  board dimension, 3 <= size <= 9 (single-digit coordinates).
 
    Returns:
        "in-progress" | "player1 is the winner" | "player2 is the winner"
 
    All moves are assumed valid, per the problem statement.
    Complexity: O(m * s^2) worst case (m moves; each topple walks at most
    s squares and each win check scans a board of at most s^2 squares).
    """
    P1, P2 = 1, 2
    STEP = {"l": (-1, 0), "r": (1, 0), "u": (0, -1), "d": (0, 1)}
    board = {}  # (x, y) -> [owner, piece_count]; absent key = open square

    def total_pieces(player):
        return sum(count for owner, count in board.values() if owner == player)

    def place(player, x, y):
        if (x, y) in board:
            board[(x, y)][1] += 1        # occupied: another piece is added
        else:
            board[(x, y)] = [player, 1]  # open: the player now owns it

    def topple(player, x, y, direction):
        """Redistribute the stack at (x, y); True if a topple happened."""
        if board.get((x, y), (None, 0))[1] < 2:
            return False                 # defensive; valid input avoids this
        in_hand = board.pop((x, y))[1]   # pick up the whole stack, square opens
        dx, dy = STEP[direction]
        while in_hand:
            x, y = x + dx, y + dy
            if not (0 <= x < size and 0 <= y < size):
                break                    # remaining pieces fall off: lost
            in_hand -= 1
            if (x, y) in board:
                board[(x, y)][1] += 1
                board[(x, y)][0] = player  # own stack grows / opponent captured
            else:
                board[(x, y)] = [player, 1]
        return True

    player, i, n = P1, 0, len(moves)
    while i < n:
        # Action 1: place (a turn always starts with a "p" move).
        move = moves[i]
        i += 1
        place(player, int(move[1]), int(move[2]))

        # Action 2: optional topple belonging to the same turn.
        if i < n and moves[i][0] == "t":
            move = moves[i]
            i += 1
            if topple(player, int(move[1]), int(move[2]), move[3]):
                # Piece counts only ever drop during a topple, so this is
                # the only moment a player can be eliminated. By the first
                # legal topple both players have already placed.
                opponent = P2 if player == P1 else P1
                if total_pieces(opponent) == 0:
                    return P1_WINS if player == P1 else P2_WINS
                if total_pieces(player) == 0:
                    # Toppled their own last pieces off the board edge.
                    return P1_WINS if opponent == P1 else P2_WINS

        player = P2 if player == P1 else P1

    return IN_PROGRESS


if __name__ == "__main__":
    TESTS = [
        ("prompt example",
         ["p01", "p22", "p01", "t01r"], 3, IN_PROGRESS),
        ("p1 captures p2's only stack",
         ["p00", "p20", "p00", "t00r"], 3, P1_WINS),
        ("p2 captures p1's only stack",
         ["p00", "p02", "p00", "p02", "t02u"], 3, P2_WINS),
        ("capture happens but opponent still has a piece elsewhere",
         ["p00", "p20", "p01", "p22", "p00", "t00r"], 3, IN_PROGRESS),
        ("one piece lands, one falls off the edge — game continues",
         ["p11", "p00", "p11", "t11d"], 3, IN_PROGRESS),
        ("player topples their own last pieces off the board",
         ["p21", "p00", "p21", "t21r"], 3, P2_WINS),
        ("longer game on 5x5, multi-square distribution",
         ["p00", "p44", "p00", "p44", "p00", "t00r"], 5, IN_PROGRESS),
        ("no moves yet",
         [], 5, IN_PROGRESS),
    ]

    for label, moves, size, expected in TESTS:
        got = get_game_status(moves, size)
        mark = "ok  " if got == expected else "FAIL"
        print(f"[{mark}] {label:<55} -> {got}")
        assert got == expected, f"{label}: expected {expected!r}, got {got!r}"

    print("\nAll tests passed.")
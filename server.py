from flask import Flask, request, jsonify

app = Flask(__name__)

# In-memory storage
players = {}
games = {}
game_players = {}

moves = {}     # game_id -> list of moves
ships = {}     # game_id -> player_id -> set of (row, col)

next_player_id = 1
next_game_id = 1

TEST_PASSWORD = "clemson-test-2026"

def check_test_auth():
    header = request.headers.get("X-Test-Password")
    if header != TEST_PASSWORD:
        return False
    return True

# -------------------------
# RESET SYSTEM
# -------------------------
@app.route("/api/reset", methods=["POST", "GET"])
def reset():
    global players, games, game_players
    global next_player_id, next_game_id

    players = {}
    games = {}
    game_players = {}

    next_player_id = 1
    next_game_id = 1

    global moves, ships

    moves = {}
    ships = {}

    return jsonify({"status": "reset"}), 200


# -------------------------
# CREATE PLAYER
# -------------------------
@app.route("/api/players", methods=["POST"])
def create_player():
    global next_player_id

    data = request.get_json(silent=True)
    if not data or "username" not in data:
        return jsonify({"error": "username required"}), 400

    username = data["username"]

    # Reject duplicate usernames
    for p in players.values():
        if p["username"] == username:
            return jsonify({"error": "duplicate username"}), 400

    player_id = next_player_id
    next_player_id += 1

    players[player_id] = {
        "username": username,
        "stats": {
            "games_played": 0,
            "wins": 0,
            "losses": 0,
            "total_shots": 0,
            "total_hits": 0
        }
    }

    return jsonify({"player_id": player_id}), 201


# -------------------------
# PLAYER STATS (REQUIRED)
# -------------------------
@app.route("/api/players/<int:player_id>/stats", methods=["GET"])
def get_player_stats(player_id):
    if player_id not in players:
        return jsonify({"error": "player not found"}), 404

    stats = players[player_id]["stats"]

    accuracy = 0
    if stats["total_shots"] > 0:
        accuracy = stats["total_hits"] / stats["total_shots"]

    return jsonify({
        "games_played": stats["games_played"],
        "wins": stats["wins"],
        "losses": stats["losses"],
        "total_shots": stats["total_shots"],
        "total_hits": stats["total_hits"],
        "accuracy": accuracy
    }), 200


# -------------------------
# CREATE GAME
# -------------------------
@app.route("/api/games", methods=["POST"])
def create_game():
    global next_game_id

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "invalid request"}), 400
    

    creator_id = data.get("creator_id")
    grid_size = data.get("grid_size")
    max_players = data.get("max_players")

    if creator_id is None or grid_size is None or max_players is None:
        return jsonify({"error": "missing fields"}), 400

    if creator_id not in players:
        return jsonify({"error": "invalid creator"}), 403

    if not isinstance(grid_size, int) or grid_size < 5 or grid_size > 15:
        return jsonify({"error": "invalid grid size"}), 400

    if not isinstance(max_players, int) or max_players < 1:
        return jsonify({"error": "invalid max players"}), 400

    game_id = next_game_id
    next_game_id += 1

    games[game_id] = {
        "game_id": game_id,
        "grid_size": grid_size,
        "max_players": max_players,
        "status": "waiting",
        "current_turn_index": 0
    }

    # Creator auto-joins
    game_players[game_id] = [creator_id]

    return jsonify({
        "game_id": game_id,
        "status": "waiting"
    }), 201

@app.route("/api/games/<int:game_id>/place", methods=["POST"])
def place_ships(game_id):
    data = request.get_json(silent=True)
    if not data or "player_id" not in data or "ships" not in data:
        return jsonify({"error": "invalid request"}), 400

    player_id = data["player_id"]
    ship_list = data["ships"]

    if game_id not in games:
        return jsonify({"error": "game not found"}), 404

    if player_id not in players:
        return jsonify({"error": "invalid player"}), 403

    if player_id not in game_players[game_id]:
        return jsonify({"error": "player not in game"}), 403

    if game_id not in ships:
        ships[game_id] = {}

    if player_id in ships[game_id]:
        return jsonify({"error": "ships already placed"}), 400

    # Validate ships (exactly 3 single-cell ships)
    if len(ship_list) != 3:
        return jsonify({"error": "must place 3 ships"}), 400

    ship_cells = set()

    for s in ship_list:
        row = s.get("row")
        col = s.get("col")

        if not isinstance(row, int) or not isinstance(col, int):
            return jsonify({"error": "invalid coordinates"}), 400

        if row < 0 or row >= games[game_id]["grid_size"] or col < 0 or col >= games[game_id]["grid_size"]:
            return jsonify({"error": "out of bounds"}), 400

        if (row, col) in ship_cells:
            return jsonify({"error": "duplicate ship placement"}), 400

        ship_cells.add((row, col))

    ships[game_id][player_id] = ship_cells

    # Activate game when all players placed ships
    if len(ships[game_id]) == len(game_players[game_id]):
        games[game_id]["status"] = "active"

    ships[game_id][player_id] = ship_cells

    # Activate game when all players have placed ships
    if len(ships[game_id]) == len(game_players[game_id]):
        games[game_id]["status"] = "active"
    return jsonify({"status": "ships placed"}), 200

@app.route("/api/test/games/<int:game_id>/restart", methods=["POST"])
def test_restart(game_id):
    if not check_test_auth():
        return jsonify({"error": "forbidden"}), 403

    if game_id not in games:
        return jsonify({"error": "game not found"}), 404

    # Clear ships and moves, reset status — player stats are PRESERVED
    ships[game_id] = {}
    moves[game_id] = []
    games[game_id]["status"] = "waiting"
    games[game_id]["current_turn_index"] = 0

    return jsonify({"status": "restarted"}), 200

@app.route("/api/test/games/<int:game_id>/ships", methods=["POST"])
def test_place_ships(game_id):
    if not check_test_auth():
        return jsonify({"error": "forbidden"}), 403

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "invalid request"}), 400

    player_id = data.get("player_id")
    ship_list = data.get("ships")

    if game_id not in games:
        return jsonify({"error": "game not found"}), 404

    if game_id not in ships:
        ships[game_id] = {}

    ship_cells = set()

    for s in ship_list:
        row = s.get("row")
        col = s.get("col")

        ship_cells.add((row, col))

    ships[game_id][player_id] = ship_cells

    return jsonify({"status": "ok"}), 200

@app.route("/api/test/games/<int:game_id>/board/<int:player_id>", methods=["GET"])
def test_board(game_id, player_id):
    if not check_test_auth():
        return jsonify({"error": "forbidden"}), 403

    if game_id not in ships:
        return jsonify({"ships": []}), 200

    player_ships = list(ships.get(game_id, {}).get(player_id, []))

    return jsonify({
        "ships": player_ships,
        "moves": moves.get(game_id, [])
    }), 200
# -------------------------
# JOIN GAME
# -------------------------
@app.route("/api/games/<int:game_id>/join", methods=["POST"])
def join_game(game_id):
    data = request.get_json(silent=True)
    if not data or "player_id" not in data:
        return jsonify({"error": "player_id required"}), 400

    player_id = data["player_id"]

    if game_id not in games:
        return jsonify({"error": "game not found"}), 404

    if player_id not in players:
        return jsonify({"error": "invalid player"}), 403

    if player_id in game_players[game_id]:
        return jsonify({"error": "already joined"}), 400

    if len(game_players[game_id]) >= games[game_id]["max_players"]:
        return jsonify({"error": "game full"}), 409

    game_players[game_id].append(player_id)

    return jsonify({"status": "joined"}), 200


# -------------------------
# GET GAME STATE
# -------------------------
@app.route("/api/games/<int:game_id>", methods=["GET"])
def get_game(game_id):
    if game_id not in games:
        return jsonify({"error": "game not found"}), 404

    game = games[game_id]

    return jsonify({
        "game_id": game["game_id"],
        "grid_size": game["grid_size"],
        "status": game["status"],
        "current_turn_index": game["current_turn_index"],
        "active_players": len(game_players[game_id])
    }), 200

# -------------------------
# Fire SHOT
# -------------------------

from datetime import datetime

@app.route("/api/games/<int:game_id>/fire", methods=["POST"])
def fire(game_id):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "invalid request"}), 400

    player_id = data.get("player_id")
    row       = data.get("row")
    col       = data.get("col")

    if game_id not in games:
        return jsonify({"error": "game not found"}), 404

    game = games[game_id]

    # Block firing in finished games
    if game["status"] == "finished":
        return jsonify({"error": "game already finished"}), 409

    # Block firing before all ships are placed
    if game["status"] != "active":
        return jsonify({"error": "game not active — all players must place ships first"}), 400

    if player_id not in players:
        return jsonify({"error": "invalid player"}), 403

    if player_id not in game_players[game_id]:
        return jsonify({"error": "player not in game"}), 403

    # Turn check
    current_turn_player = game_players[game_id][game["current_turn_index"]]
    if player_id != current_turn_player:
        return jsonify({"error": "not your turn"}), 403

    # Bounds check
    if not isinstance(row, int) or not isinstance(col, int):
        return jsonify({"error": "invalid coordinates"}), 400

    if row < 0 or row >= game["grid_size"] or col < 0 or col >= game["grid_size"]:
        return jsonify({"error": "out of bounds"}), 400

    if game_id not in moves:
        moves[game_id] = []

    # Hit detection — check ALL opponents' ships
    hit = False
    for pid, ship_cells in ships.get(game_id, {}).items():
        if pid != player_id and (row, col) in ship_cells:
            hit = True
            ship_cells.discard((row, col))
            break

    result = "hit" if hit else "miss"

    # Update shooter stats
    players[player_id]["stats"]["total_shots"] += 1
    if hit:
        players[player_id]["stats"]["total_hits"] += 1

    # Log move
    moves[game_id].append({
        "player_id": player_id,
        "row":       row,
        "col":       col,
        "result":    result,
        "timestamp": datetime.utcnow().isoformat()
    })

    # Win condition — are all opponents out of ships?
    living_opponents = [
        p for p in game_players[game_id]
        if p != player_id and len(ships.get(game_id, {}).get(p, set())) > 0
    ]

    if len(living_opponents) == 0:
        game["status"] = "finished"

        # Update stats for everyone
        for pid in game_players[game_id]:
            players[pid]["stats"]["games_played"] += 1
            if pid == player_id:
                players[pid]["stats"]["wins"] += 1
            else:
                players[pid]["stats"]["losses"] += 1

        return jsonify({
            "result":         result,
            "next_player_id": None,
            "game_status":    "finished",
            "winner_id":      player_id
        }), 200

    # Advance turn — skip players with no ships left
    n   = len(game_players[game_id])
    idx = game["current_turn_index"]
    for _ in range(n):
        idx = (idx + 1) % n
        candidate = game_players[game_id][idx]
        if len(ships.get(game_id, {}).get(candidate, set())) > 0:
            break
    game["current_turn_index"] = idx
    next_player = game_players[game_id][idx]

    return jsonify({
        "result":         result,
        "next_player_id": next_player,
        "game_status":    "active"
    }), 200

@app.route("/api/games/<int:game_id>/moves", methods=["GET"])
def get_moves(game_id):
    return jsonify(moves.get(game_id, [])), 200
# -------------------------
# RUN SERVER
# -------------------------
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

from flask import Flask, request, jsonify

app = Flask(__name__)

# In-memory storage
players = {}
games = {}
game_players = {}

next_player_id = 1
next_game_id = 1


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
        return jsonify({"error": "game full"}), 400

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
# RUN SERVER
# -------------------------
if __name__ == "__main__":
    app.run(debug=True)
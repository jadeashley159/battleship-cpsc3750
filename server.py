from flask import Flask, request, jsonify

app = Flask(__name__)

players = {}
games = {}
game_players = {}

next_player_id = 1
next_game_id = 1


@app.route("/api/reset", methods=["POST"])
def reset():
    global players, games, game_players
    global next_player_id, next_game_id

    players = {}
    games = {}
    game_players = {}

    next_player_id = 1
    next_game_id = 1

    return jsonify({"status": "reset"}), 200


@app.route("/api/players", methods=["POST"])
def create_player():
    global next_player_id

    data = request.json
    username = data.get("username")

    if not username:
        return jsonify({"error": "username required"}), 400

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


@app.route("/api/games", methods=["POST"])
def create_game():
    global next_game_id

    data = request.json
    creator_id = data.get("creator_id")
    grid_size = data.get("grid_size")
    max_players = data.get("max_players")

    if creator_id not in players:
        return jsonify({"error": "invalid creator"}), 403

    if grid_size < 5 or grid_size > 15:
        return jsonify({"error": "invalid grid size"}), 400

    if max_players < 1:
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

    game_players[game_id] = [creator_id]

    return jsonify({
        "game_id": game_id,
        "status": "waiting"
    }), 201


@app.route("/api/games/<int:game_id>/join", methods=["POST"])
def join_game(game_id):
    data = request.json
    player_id = data.get("player_id")

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


if __name__ == "__main__":
    app.run(debug=True)
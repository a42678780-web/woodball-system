from flask import Flask, render_template, request, jsonify, redirect, send_file
from flask_socketio import SocketIO
import os
import json
import csv
import io
from datetime import datetime

app = Flask(__name__)
app.config["SECRET_KEY"] = "woodball_secret"
socketio = SocketIO(app, cors_allowed_origins="*")

MATCH_DIR = "matches"
OUTPUT_DIR = "output"
CURRENT_FILE = "current_match.txt"

os.makedirs(MATCH_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def default_course(match_name="木球賽事", match_type="桿數賽"):
    holes = {}
    for i in range(1, 13):
        holes[str(i)] = {
            "par": 4,
            "distance": 60
        }

    return {
        "match_name": match_name,
        "match_type": match_type,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "holes": holes,
        "players": {}
    }


def safe_filename(name):
    name = name.strip().replace(" ", "_")
    remove_chars = '\\/:*?"<>|'

    for ch in remove_chars:
        name = name.replace(ch, "")

    if not name:
        name = "woodball_match"

    return name + ".json"


def set_current_match_file(filename):
    with open(CURRENT_FILE, "w", encoding="utf-8") as f:
        f.write(filename)


def get_current_match_file():
    if os.path.exists(CURRENT_FILE):
        with open(CURRENT_FILE, "r", encoding="utf-8") as f:
            filename = f.read().strip()

        if filename:
            path = os.path.join(MATCH_DIR, filename)
            if os.path.exists(path):
                return filename

    filename = "default_match.json"
    path = os.path.join(MATCH_DIR, filename)

    if not os.path.exists(path):
        course = default_course()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(course, f, ensure_ascii=False, indent=4)

    set_current_match_file(filename)
    return filename


def save_course(course, filename=None):
    if filename is None:
        filename = get_current_match_file()

    path = os.path.join(MATCH_DIR, filename)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(course, f, ensure_ascii=False, indent=4)


def load_course_by_filename(filename):
    path = os.path.join(MATCH_DIR, filename)

    with open(path, "r", encoding="utf-8") as f:
        course = json.load(f)

    if "holes" not in course:
        course["holes"] = default_course()["holes"]

    if "players" not in course:
        course["players"] = {}

    for i in range(1, 13):
        if str(i) not in course["holes"]:
            course["holes"][str(i)] = {
                "par": 4,
                "distance": 60
            }

    for pid, player in course["players"].items():
        player.setdefault("number", "")
        player.setdefault("city", "")
        player.setdefault("school", "")
        player.setdefault("group", "")
        player.setdefault("name", "")
        player.setdefault("scores", {})

    return course


def load_course():
    filename = get_current_match_file()
    return load_course_by_filename(filename)


def get_all_matches():
    matches = []

    for filename in os.listdir(MATCH_DIR):
        if not filename.endswith(".json"):
            continue

        path = os.path.join(MATCH_DIR, filename)

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            matches.append({
                "filename": filename,
                "name": data.get("match_name", filename),
                "type": data.get("match_type", "桿數賽")
            })
        except:
            pass

    matches.sort(key=lambda x: x["name"])
    return matches


def get_groups(course):
    groups = set()

    for player in course.get("players", {}).values():
        group = player.get("group", "").strip()
        if group:
            groups.add(group)

    return sorted(list(groups))


def number_sort_value(value):
    text = str(value).strip()
    if text.startswith("#"):
        text = text[1:]
    return int(text) if text.isdigit() else 9999




def calc_total_par(course):
    total_par = 0
    for i in range(1, 13):
        try:
            total_par += int(course.get("holes", {}).get(str(i), {}).get("par", 0) or 0)
        except:
            pass
    return total_par


def format_plus_minus(value):
    try:
        diff = int(value)
    except:
        return ""

    if diff > 0:
        return "+" + str(diff)
    elif diff < 0:
        return str(diff)
    else:
        return "E"


def calc_player_plus_minus(course, player):
    total = calc_player_total(player)

    if total <= 0:
        return ""

    return format_plus_minus(total - calc_total_par(course))


def calc_player_total(player):
    scores = player.get("scores", {})
    total = 0

    for i in range(1, 13):
        value = scores.get(str(i), "")

        if value == "":
            continue

        try:
            total += int(value)
        except:
            pass

    return total


def sorted_players(course):
    players = []

    for pid, player in course.get("players", {}).items():
        item = dict(player)

        item["id"] = pid
        item["number"] = item.get("number", "")
        item["city"] = item.get("city", "")
        item["school"] = item.get("school", "")
        item["group"] = item.get("group", "")
        item["name"] = item.get("name", "")
        item["scores"] = item.get("scores", {})
        item["total"] = calc_player_total(player)
        item["plus_minus"] = calc_player_plus_minus(course, player)

        players.append(item)

    players.sort(
        key=lambda x: (
            x["group"],
            number_sort_value(x["number"]),
            x["school"],
            x["name"]
        )
    )

    return players


def team_rows(course):
    teams = {}
    total_par = calc_total_par(course)

    for idx, player in enumerate(course.get("players", {}).values()):
        number = player.get("number", "")
        city = player.get("city", "")
        school = player.get("school", "")
        group = player.get("group", "")
        name = player.get("name", "")

        key = f"{number}|{city}|{school}|{group}"

        if key not in teams:
            teams[key] = {
                "order": idx,
                "number": number,
                "city": city,
                "school": school,
                "group": group,
                "players": [],
                "total_score": 0,
                "has_score": False
            }

        if name:
            teams[key]["players"].append(name)

        player_total = calc_player_total(player)

        if player_total > 0:
            teams[key]["total_score"] += player_total
            teams[key]["has_score"] = True

    result = []

    for item in teams.values():
        while len(item["players"]) < 4:
            item["players"].append("")

        item["player1"] = item["players"][0]
        item["player2"] = item["players"][1]
        item["player3"] = item["players"][2]
        item["player4"] = item["players"][3]

        if item["has_score"]:
            item["plus_minus"] = format_plus_minus(item["total_score"] - total_par)
        else:
            item["total_score"] = 0
            item["plus_minus"] = ""

        result.append(item)

    result.sort(
        key=lambda x: (
            x["group"],
            number_sort_value(x["number"]),
            x["school"]
        )
    )

    return result


def output_player_row(course, player, hole):
    hole = str(hole)

    hole_data = course.get("holes", {}).get(hole, {})
    par = hole_data.get("par", "")
    distance = hole_data.get("distance", "")

    scores = player.get("scores", {})
    current_score = scores.get(hole, "")

    total_score = player.get("total", calc_player_total(player))
    plus_minus = player.get("plus_minus", calc_player_plus_minus(course, player))

    return {
        "match_name": course.get("match_name", "") or "-",
        "match_type": course.get("match_type", "") or "-",
        "hole": "H" + hole,
        "par": par if par != "" else 0,
        "distance": str(distance) + "M" if distance != "" else "-",
        "total_score": total_score,
        "plus_minus": plus_minus,
        "current_score": current_score if current_score != "" else 0,
        "group": player.get("group", "") or "-",
        "number": player.get("number", "") or "-",
        "city": player.get("city", "") or "-",
        "school": player.get("school", "") or "-",
        "player_name": player.get("name", "") or "-"
    }


def find_player_by_id(course, player_id):
    players = sorted_players(course)

    for player in players:
        if str(player.get("id", "")) == str(player_id):
            return player

    return None


def ranking_json_rows(course, group_name="all"):
    teams = {}
    order_index = 0
    total_par = calc_total_par(course)

    for player in course.get("players", {}).values():
        number = player.get("number", "")
        city = player.get("city", "")
        school = player.get("school", "")
        group = player.get("group", "")
        name = player.get("name", "")

        if group_name != "all" and group != group_name:
            continue

        key = f"{number}|{city}|{school}|{group}"

        if key not in teams:
            teams[key] = {
                "order": order_index,
                "number": number,
                "city": city,
                "school": school,
                "group": group,
                "players": [],
                "total_score": 0,
                "has_score": False
            }
            order_index += 1

        if name:
            teams[key]["players"].append(name)

        player_total = calc_player_total(player)

        if player_total > 0:
            teams[key]["has_score"] = True
            teams[key]["total_score"] += player_total

    team_list = list(teams.values())

    if any(t["has_score"] for t in team_list):
        scored = [t for t in team_list if t["has_score"]]
        unscored = [t for t in team_list if not t["has_score"]]

        scored.sort(key=lambda x: x["total_score"])
        unscored.sort(key=lambda x: (x["order"], number_sort_value(x["number"])))

        team_list = scored + unscored
    else:
        team_list.sort(key=lambda x: (x["order"], number_sort_value(x["number"])))

    rows = []

    for rank, team in enumerate(team_list, start=1):
        names = team["players"][:4]

        while len(names) < 4:
            names.append("")

        if team["has_score"]:
            plus_minus = format_plus_minus(team["total_score"] - total_par)
        else:
            plus_minus = ""

        rows.append({
            "rank": rank,
            "number": team["number"],
            "city": team["city"],
            "school": team["school"],
            "group": team["group"],
            "player_name": names[0],
            "player2_name": names[1],
            "player3_name": names[2],
            "player4_name": names[3],
            "total_score": team["total_score"] if team["has_score"] else 0,
            "plus_minus": plus_minus
        })

    return rows


def save_json_output(filename, data):
    path = os.path.join(OUTPUT_DIR, filename)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    return path


def next_player_id(course):
    players = course.get("players", {})

    if not players:
        return "1"

    nums = []

    for pid in players.keys():
        try:
            nums.append(int(pid))
        except:
            pass

    if not nums:
        return str(len(players) + 1)

    return str(max(nums) + 1)


@app.route("/")
def index():
    return redirect("/admin")


@app.route("/admin")
def admin():
    course = load_course()
    current_file = get_current_match_file()
    players = sorted_players(course)
    teams = team_rows(course)
    groups = get_groups(course)
    all_matches = get_all_matches()

    return render_template(
        "admin.html",
        course=course,
        players=players,
        team_rows=teams,
        groups=groups,
        all_matches=all_matches,
        current_file=current_file
    )




@app.route("/referee")
def referee_match_select():
    return render_template(
        "referee_match_select.html",
        all_matches=get_all_matches(),
        current_file=get_current_match_file()
    )


@app.route("/referee/select/<match_filename>")
def referee_player_select(match_filename):
    path = os.path.join(MATCH_DIR, match_filename)

    if not os.path.exists(path):
        return "找不到賽事檔案", 404

    course = load_course_by_filename(match_filename)
    players = sorted_players(course)

    return render_template(
        "referee_player_select.html",
        match_filename=match_filename,
        course=course,
        players=players
    )


@app.route("/referee/score/<match_filename>")
def referee_mobile_score(match_filename):
    path = os.path.join(MATCH_DIR, match_filename)

    if not os.path.exists(path):
        return "找不到賽事檔案", 404

    player_ids = request.args.get("players", "")
    selected_ids = [x for x in player_ids.split(",") if x.strip()]

    if not selected_ids:
        return redirect("/referee/select/" + match_filename)

    course = load_course_by_filename(match_filename)
    players = []

    for player_id in selected_ids[:4]:
        player = find_player_by_id(course, player_id)
        if player is not None:
            players.append(player)

    if not players:
        return redirect("/referee/select/" + match_filename)

    return render_template(
        "referee_mobile_score.html",
        match_filename=match_filename,
        course=course,
        players=players
    )


@app.route("/referee/overview/<match_filename>")
def referee_mobile_overview(match_filename):
    path = os.path.join(MATCH_DIR, match_filename)

    if not os.path.exists(path):
        return "找不到賽事檔案", 404

    course = load_course_by_filename(match_filename)
    players = sorted_players(course)

    return render_template(
        "referee_mobile_overview.html",
        match_filename=match_filename,
        course=course,
        players=players
    )


@app.route("/api/referee_get_score", methods=["POST"])
def api_referee_get_score():
    data = request.get_json()
    match_filename = data.get("match_filename", "")
    player_id = str(data.get("player_id", ""))
    hole = str(data.get("hole", "1"))

    path = os.path.join(MATCH_DIR, match_filename)

    if not os.path.exists(path):
        return jsonify({"status": "error", "message": "找不到賽事"})

    course = load_course_by_filename(match_filename)

    if player_id not in course["players"]:
        return jsonify({"status": "error", "message": "找不到選手"})

    score = course["players"][player_id].get("scores", {}).get(hole, 0)

    try:
        score = int(score)
    except:
        score = 0

    return jsonify({
        "status": "success",
        "score": score
    })


@app.route("/api/referee_update_score", methods=["POST"])
def api_referee_update_score():
    data = request.get_json()

    match_filename = data.get("match_filename", "")
    player_id = str(data.get("player_id", ""))
    hole = str(data.get("hole", ""))
    score = data.get("score", 0)

    path = os.path.join(MATCH_DIR, match_filename)

    if not os.path.exists(path):
        return jsonify({"status": "error", "message": "找不到賽事"})

    course = load_course_by_filename(match_filename)

    if player_id not in course["players"]:
        return jsonify({"status": "error", "message": "找不到選手"})

    try:
        score = int(score)
    except:
        score = 0

    if score < 0:
        score = 0

    course["players"][player_id].setdefault("scores", {})
    course["players"][player_id]["scores"][hole] = score

    save_course(course, match_filename)

    socketio.emit("leaderboard_update")

    return jsonify({
        "status": "success",
        "score": score
    })


@app.route("/api/referee_hole_info", methods=["POST"])
def api_referee_hole_info():
    data = request.get_json()
    match_filename = data.get("match_filename", "")
    hole = str(data.get("hole", "1"))

    path = os.path.join(MATCH_DIR, match_filename)

    if not os.path.exists(path):
        return jsonify({"status": "error", "message": "找不到賽事"})

    course = load_course_by_filename(match_filename)
    hole_data = course.get("holes", {}).get(hole, {})

    return jsonify({
        "status": "success",
        "par": hole_data.get("par", ""),
        "distance": hole_data.get("distance", "")
    })


@app.route("/output/personal.json")
def output_personal_json_file():
    path = os.path.join(OUTPUT_DIR, "personal.json")

    if not os.path.exists(path):
        return jsonify({
            "status": "error",
            "message": "尚未輸出 personal.json，請先到後台按輸出"
        }), 404

    return send_file(path, mimetype="application/json")


@app.route("/output/pair.json")
def output_pair_json_file():
    path = os.path.join(OUTPUT_DIR, "double.json")

    if not os.path.exists(path):
        return jsonify({
            "status": "error",
            "message": "尚未輸出 double.json，請先到後台按輸出"
        }), 404

    return send_file(path, mimetype="application/json")


@app.route("/output/double.json")
def output_double_json_file():
    path = os.path.join(OUTPUT_DIR, "double.json")

    if not os.path.exists(path):
        return jsonify({
            "status": "error",
            "message": "尚未輸出 double.json，請先到後台按輸出"
        }), 404

    return send_file(path, mimetype="application/json")


@app.route("/output/ranking.json")
def output_ranking_json_file():
    path = os.path.join(OUTPUT_DIR, "rank.json")

    if not os.path.exists(path):
        return jsonify({
            "status": "error",
            "message": "尚未輸出 rank.json，請先到後台按輸出"
        }), 404

    return send_file(path, mimetype="application/json")


@app.route("/output/rank.json")
def output_rank_json_file():
    path = os.path.join(OUTPUT_DIR, "rank.json")

    if not os.path.exists(path):
        return jsonify({
            "status": "error",
            "message": "尚未輸出 rank.json，請先到後台按輸出"
        }), 404

    return send_file(path, mimetype="application/json")


@app.route("/api/create_match", methods=["POST"])
def api_create_match():
    data = request.get_json()

    match_name = data.get("match_name", "").strip()
    match_type = data.get("match_type", "桿數賽")

    if not match_name:
        return jsonify({
            "status": "error",
            "message": "賽事名稱不可空白"
        })

    filename = safe_filename(match_name)
    path = os.path.join(MATCH_DIR, filename)

    count = 1
    base_filename = filename

    while os.path.exists(path):
        filename = base_filename.replace(".json", f"_{count}.json")
        path = os.path.join(MATCH_DIR, filename)
        count += 1

    course = default_course(match_name, match_type)
    save_course(course, filename)
    set_current_match_file(filename)

    return jsonify({
        "status": "success"
    })


@app.route("/api/load_match", methods=["POST"])
def api_load_match():
    data = request.get_json()
    filename = data.get("filename", "")

    path = os.path.join(MATCH_DIR, filename)

    if not os.path.exists(path):
        return jsonify({
            "status": "error",
            "message": "找不到賽事檔案"
        })

    set_current_match_file(filename)

    return jsonify({
        "status": "success"
    })


@app.route("/api/delete_match", methods=["POST"])
def api_delete_match():
    data = request.get_json()
    filename = data.get("filename", "")

    path = os.path.join(MATCH_DIR, filename)

    if not os.path.exists(path):
        return jsonify({
            "status": "error",
            "message": "找不到賽事檔案"
        })

    os.remove(path)

    matches = get_all_matches()

    if matches:
        set_current_match_file(matches[0]["filename"])
    else:
        new_file = "default_match.json"
        save_course(default_course(), new_file)
        set_current_match_file(new_file)

    return jsonify({
        "status": "success"
    })


@app.route("/api/update_course", methods=["POST"])
def api_update_course():
    data = request.get_json()
    holes = data.get("holes", {})

    course = load_course()
    course["holes"] = holes

    save_course(course)

    return jsonify({
        "status": "success"
    })


@app.route("/api/add_player", methods=["POST"])
def api_add_player():
    data = request.get_json()

    number = data.get("number", "").strip()
    city = data.get("city", "").strip()
    school = data.get("school", "").strip()
    group = data.get("group", "").strip()
    name = data.get("name", "").strip()

    if not name or not group:
        return jsonify({
            "status": "error",
            "message": "姓名與組別不可空白"
        })

    course = load_course()
    pid = next_player_id(course)

    course["players"][pid] = {
        "number": number,
        "city": city,
        "school": school,
        "group": group,
        "name": name,
        "scores": {}
    }

    save_course(course)

    return jsonify({
        "status": "success"
    })


@app.route("/api/edit_player", methods=["POST"])
def api_edit_player():
    data = request.get_json()

    player_id = str(data.get("player_id", ""))
    number = data.get("number", "").strip()
    city = data.get("city", "").strip()
    school = data.get("school", "").strip()
    group = data.get("group", "").strip()
    name = data.get("name", "").strip()

    course = load_course()

    if player_id not in course["players"]:
        return jsonify({
            "status": "error",
            "message": "找不到球員"
        })

    course["players"][player_id]["number"] = number
    course["players"][player_id]["city"] = city
    course["players"][player_id]["school"] = school
    course["players"][player_id]["group"] = group
    course["players"][player_id]["name"] = name

    if "scores" not in course["players"][player_id]:
        course["players"][player_id]["scores"] = {}

    save_course(course)

    return jsonify({
        "status": "success"
    })


@app.route("/api/delete_player", methods=["POST"])
def api_delete_player():
    data = request.get_json()
    player_id = str(data.get("player_id", ""))

    course = load_course()

    if player_id in course["players"]:
        del course["players"][player_id]

    save_course(course)

    return jsonify({
        "status": "success"
    })


@app.route("/api/upload_players", methods=["POST"])
def api_upload_players():
    if "file" not in request.files:
        return jsonify({
            "status": "error",
            "message": "沒有收到檔案"
        })

    file = request.files["file"]

    if file.filename == "":
        return jsonify({
            "status": "error",
            "message": "檔案名稱空白"
        })

    raw_data = file.read()

    try:
        content = raw_data.decode("utf-8-sig")
    except:
        try:
            content = raw_data.decode("big5")
        except:
            return jsonify({
                "status": "error",
                "message": "CSV 編碼錯誤，請另存 UTF-8 CSV"
            })

    reader = csv.reader(io.StringIO(content))
    rows = list(reader)

    if len(rows) <= 1:
        return jsonify({
            "status": "error",
            "message": "CSV 沒有資料"
        })

    course = load_course()
    count = 0

    for idx, row in enumerate(rows):
        if idx == 0:
            continue

        if len(row) < 8:
            continue

        number = row[0].strip()
        city = row[1].strip()
        school = row[2].strip()
        group = row[3].strip()

        names = [
            row[4].strip(),
            row[5].strip(),
            row[6].strip(),
            row[7].strip()
        ]

        for name in names:
            if not name:
                continue

            pid = next_player_id(course)

            course["players"][pid] = {
                "number": number,
                "city": city,
                "school": school,
                "group": group,
                "name": name,
                "scores": {}
            }

            count += 1

    save_course(course)

    return jsonify({
        "status": "success",
        "count": count
    })


@app.route("/api/output_personal_json", methods=["POST"])
def api_output_personal_json():
    data = request.get_json()
    player_id = str(data.get("player_id", ""))
    hole = str(data.get("hole", "1"))

    course = load_course()
    player = find_player_by_id(course, player_id)

    if player is None:
        return jsonify({
            "status": "error",
            "message": "找不到選手"
        })

    row = output_player_row(course, player, hole)

    save_json_output("personal.json", [row])

    return jsonify({
        "status": "success",
        "file": "/output/personal.json"
    })


@app.route("/api/output_pair_json", methods=["POST"])
def api_output_pair_json():
    data = request.get_json()

    upper_player_id = str(data.get("upper_player_id", ""))
    lower_player_id = str(data.get("lower_player_id", ""))
    hole = str(data.get("hole", "1"))

    course = load_course()

    upper_player = find_player_by_id(course, upper_player_id)
    lower_player = find_player_by_id(course, lower_player_id)

    if upper_player is None:
        return jsonify({
            "status": "error",
            "message": "找不到上方選手"
        })

    if lower_player is None:
        return jsonify({
            "status": "error",
            "message": "找不到下方選手"
        })

    upper_row = output_player_row(course, upper_player, hole)
    lower_row = output_player_row(course, lower_player, hole)

    upper_row["position"] = "upper"
    lower_row["position"] = "lower"

    output_data = [
        upper_row,
        lower_row
    ]

    save_json_output("double.json", output_data)

    return jsonify({
        "status": "success",
        "file": "/output/double.json"
    })


@app.route("/api/output_ranking_json", methods=["POST"])
def api_output_ranking_json():
    data = request.get_json()

    group_name = data.get("group", "all")
    match_filename = data.get("match_filename", "")

    if match_filename:
        path = os.path.join(MATCH_DIR, match_filename)

        if not os.path.exists(path):
            return jsonify({
                "status": "error",
                "message": "找不到指定賽事檔案"
            })

        course = load_course_by_filename(match_filename)
    else:
        course = load_course()

    rows = ranking_json_rows(course, group_name)

    save_json_output("rank.json", rows)

    return jsonify({
        "status": "success",
        "file": "/output/rank.json",
        "count": len(rows)
    })


@app.route("/api/update_score", methods=["POST"])
def api_update_score():
    data = request.get_json()

    player_id = str(data.get("player_id"))
    hole = str(data.get("hole"))
    score = data.get("score", "")

    course = load_course()

    if player_id not in course["players"]:
        return jsonify({"status": "error", "message": "找不到選手"})

    course["players"][player_id].setdefault("scores", {})

    if score == "":
        course["players"][player_id]["scores"].pop(hole, None)
    else:
        try:
            course["players"][player_id]["scores"][hole] = int(score)
        except:
            return jsonify({"status": "error", "message": "成績必須是數字"})

    save_course(course)

    return jsonify({"status": "success"})


@app.route("/api/update_scores_bulk", methods=["POST"])
def api_update_scores_bulk():
    data = request.get_json()
    updates = data.get("updates", [])

    course = load_course()

    for item in updates:
        player_id = str(item.get("player_id", ""))
        hole = str(item.get("hole", ""))
        score = item.get("score", "")

        if player_id not in course["players"]:
            continue

        course["players"][player_id].setdefault("scores", {})

        if score == "":
            course["players"][player_id]["scores"].pop(hole, None)
        else:
            try:
                course["players"][player_id]["scores"][hole] = int(score)
            except:
                continue

    save_course(course)

    return jsonify({
        "status": "success",
        "count": len(updates)
    })


@app.route("/export/csv/<mode>")
def export_csv(mode):
    course = load_course()
    players = sorted_players(course)

    if mode.startswith("group_"):
        group_name = mode.replace("group_", "")
        players = [p for p in players if p.get("group") == group_name]
        filename = f"{group_name}_成績.csv"
    else:
        filename = f"{course.get('match_name', 'woodball')}_成績.csv"

    output = io.StringIO()
    writer = csv.writer(output)

    header = [
        "排名",
        "編號",
        "縣市",
        "學校",
        "組別",
        "姓名"
    ]

    for i in range(1, 13):
        header.append(f"第{i}洞")

    header.append("總桿數")
    header.append("+/-")

    writer.writerow(header)

    total_par = 0

    for i in range(1, 13):
        total_par += int(course["holes"].get(str(i), {}).get("par", 0) or 0)

    for rank, player in enumerate(players, start=1):
        row = [
            rank,
            player.get("number", ""),
            player.get("city", ""),
            player.get("school", ""),
            player.get("group", ""),
            player.get("name", "")
        ]

        scores = player.get("scores", {})

        for i in range(1, 13):
            row.append(scores.get(str(i), ""))

        total = player.get("total", 0)

        if total > 0:
            plus_minus = format_plus_minus(total - total_par)
        else:
            plus_minus = ""

        row.append(total)
        row.append(plus_minus)

        writer.writerow(row)

    mem = io.BytesIO()
    mem.write(output.getvalue().encode("utf-8-sig"))
    mem.seek(0)

    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename
    )


@socketio.on("submit_score")
def handle_submit_score(data):
    player_id = str(data.get("player_id", ""))
    hole = str(data.get("hole", ""))
    score = int(data.get("score", 0) or 0)

    course = load_course()

    if player_id not in course["players"]:
        return

    if "scores" not in course["players"][player_id]:
        course["players"][player_id]["scores"] = {}

    course["players"][player_id]["scores"][hole] = score

    save_course(course)

    socketio.emit("leaderboard_update")


if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=True,
        allow_unsafe_werkzeug=True
    )

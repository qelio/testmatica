from datetime import date, timedelta

from .conftest import add_person, bearer
from .test_journal import grade_type_id, put_grade, setup  # noqa: F401 — фикстура

PERIOD = {"from": (date.today() - timedelta(days=30)).isoformat(), "to": date.today().isoformat(), "tz": "Europe/Moscow"}


async def fill(client, world, setup):
    t, anya, petya = setup["teacher"], setup["anya"], setup["petya"]
    type_id = await grade_type_id(client, t)
    await put_grade(client, t, setup["past1"], anya, 5, type_id)
    await put_grade(client, t, setup["past1"], anya, 4, type_id)
    await put_grade(client, t, setup["past2"], petya, 3, type_id)
    await client.post(f"/lessons/{setup['past1']}/attendance/all-present", headers=bearer(t))
    await client.put(f"/lessons/{setup['past2']}/attendance/{anya}", json={"status": "absent"}, headers=bearer(t))
    await client.put(f"/lessons/{setup['past2']}/attendance/{petya}", json={"status": "present"}, headers=bearer(t))


async def test_group_analytics_free_and_basic(client, world, setup):
    t, gid = setup["teacher"], setup["gid"]
    await fill(client, world, setup)

    # Бесплатный тариф — средний балл и посещаемость, без динамики, сравнения и выгрузки.
    free = (await client.get(f"/analytics/groups/{gid}", params=PERIOD, headers=bearer(t))).json()
    assert free["extended"] is False and free["stats"]["average"] == 4.0 and free["trend"] is None
    assert [(s["full_name"], s["stats"]["average"], s["delta"]) for s in free["students"]] == [("Аня", 4.5, None), ("Петя", 3.0, None)]
    denied = await client.get(f"/analytics/groups/{gid}/export", params=PERIOD | {"format": "xlsx"}, headers=bearer(t))
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "plan_required"
    assert (await client.get("/analytics/summary", params=PERIOD, headers=bearer(t))).status_code == 403

    world.basic.add(str(t))
    full = (await client.get(f"/analytics/groups/{gid}", params=PERIOD, headers=bearer(t))).json()
    assert full["extended"] is True
    assert {s["full_name"]: s["delta"] for s in full["students"]} == {"Аня": 0.5, "Петя": -1.0}  # сравнение с классом
    assert full["distribution"] == {"1": 0, "2": 0, "3": 1, "4": 1, "5": 1}
    assert len(full["trend"]) >= 1 and full["trend"][0]["average"] is not None
    missed = {h["day"]: (h["missed"], h["marked"]) for h in full["heatmap"]}
    assert sorted(missed.values()) == [(0, 2), (1, 2)]  # день без пропусков и день, когда Аня отсутствовала

    xlsx = await client.get(f"/analytics/groups/{gid}/export", params=PERIOD | {"format": "xlsx"}, headers=bearer(t))
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK" and "spreadsheetml" in xlsx.headers["content-type"]
    pdf = await client.get(f"/analytics/groups/{gid}/export", params=PERIOD | {"format": "pdf"}, headers=bearer(t))
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    # Чужая группа — 404, кривой период — 422.
    other = world.group(setup["anya"], [])
    assert (await client.get(f"/analytics/groups/{other}", params=PERIOD, headers=bearer(t))).status_code == 404
    bad = PERIOD | {"from": "2020-01-01"}
    assert (await client.get(f"/analytics/groups/{gid}", params=bad, headers=bearer(t))).status_code == 422


async def test_student_analytics_and_summary(client, world, setup):
    t, anya = setup["teacher"], setup["anya"]
    await fill(client, world, setup)
    world.basic.add(str(t))
    world.links.add((str(t), str(anya)))
    # Индивидуальное занятие Ани по физике.
    solo = world.lesson(t, [anya], -1, student_id=anya, subject="Физика")
    type_id = await grade_type_id(client, t)
    await put_grade(client, t, solo, anya, 2, type_id, "Не готова")

    r = (await client.get(f"/analytics/students/{anya}", params=PERIOD, headers=bearer(t))).json()
    subjects = {s["subject"]: (s["stats"]["average"], s["class_average"]) for s in r["subjects"]}
    assert subjects == {"Алгебра": (4.5, 4.0), "Физика": (2.0, None)}
    assert [g["value"] for g in r["grades"]] == [5, 4, 2] and r["stats"]["attendance_rate"] == 0.5
    assert (await client.get(f"/analytics/students/{anya}/export", params=PERIOD | {"format": "pdf"},
                             headers=bearer(t))).content.startswith(b"%PDF")

    await add_person(setup["petya"], "Петя")
    s = (await client.get("/analytics/summary", params=PERIOD, headers=bearer(t))).json()
    rows = {row["title"]: row for row in s["rows"]}
    assert rows["7А"]["students"] == 2 and rows["7А"]["stats"]["average"] == 4.0 and rows["7А"]["below_three"] == 0
    assert rows["Индивидуальные занятия"]["below_three"] == 1 and s["total"]["grades_count"] == 4
    for fmt in ("xlsx", "pdf"):
        assert (await client.get("/analytics/summary/export", params=PERIOD | {"format": fmt}, headers=bearer(t))).status_code == 200

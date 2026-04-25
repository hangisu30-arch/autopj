from app.ui.json_validator import validate_file_ops_json


def test_validate_file_ops_json_accepts_mvnw_without_path_comment():
    ok, err = validate_file_ops_json('[{"path":"mvnw","purpose":"wrapper","content":"#!/bin/sh\\necho ok\\n"}]', frontend_key="jsp")
    assert ok, err


def test_validate_file_ops_json_accepts_mvnw_cmd_without_path_comment():
    ok, err = validate_file_ops_json('[{"path":"mvnw.cmd","purpose":"wrapper","content":"@echo off\\necho ok\\n"}]', frontend_key="jsp")
    assert ok, err


def test_validate_file_ops_json_accepts_gradlew_without_path_comment():
    ok, err = validate_file_ops_json('[{"path":"gradlew","purpose":"wrapper","content":"#!/bin/sh\\necho ok\\n"}]', frontend_key="jsp")
    assert ok, err

from execution_core.builtin_crud import builtin_file, infer_schema_from_plan


def test_explicit_requirement_columns_override_authoritative_analysis_defaults():
    plan = {
        'tasks': [
            {'path': 'src/main/java/egovframework/demo/schedule/web/ScheduleController.java'},
        ],
        'domains': [
            {
                'name': 'schedule',
                'entity_name': 'Schedule',
                'source_table': 'schedule',
                'fields': [
                    {'name': 'scheduleId', 'column': 'schedule_id', 'java_type': 'Long'},
                    {'name': 'title', 'column': 'title', 'java_type': 'String'},
                    {'name': 'content', 'column': 'content', 'java_type': 'String'},
                    {'name': 'writerId', 'column': 'writer_id', 'java_type': 'String'},
                ],
            }
        ],
        'requirements_text': '''
DB 규칙:
- 테이블명은 schedule 로 사용한다
- 컬럼은 아래를 사용한다
  - schedule_id
  - title
  - owner_empno
  - start_at
  - end_at
''',
    }
    schema = infer_schema_from_plan(plan)
    assert schema.table == 'schedule'
    assert [col for _prop, col, _jt in schema.fields] == [
        'schedule_id', 'title', 'owner_empno', 'start_at', 'end_at'
    ]


def test_generated_crud_stack_adds_search_map_signatures_and_dynamic_filters():
    schema = infer_schema_from_plan({
        'tasks': [{'path': 'src/main/java/egovframework/demo/board/web/BoardController.java'}],
        'requirements_text': '''
- 테이블명은 board
- 컬럼은 아래를 사용한다
  - board_id
  - title
  - content
  - writer_id
  - use_yn
  - reg_dt
''',
    })

    service_java = builtin_file('java/service/BoardService.java', 'egovframework.demo.board', schema)
    service_impl_java = builtin_file('java/service/impl/BoardServiceImpl.java', 'egovframework.demo.board', schema)
    mapper_java = builtin_file('java/service/mapper/BoardMapper.java', 'egovframework.demo.board', schema)
    controller_java = builtin_file('java/controller/BoardController.java', 'egovframework.demo.board', schema)
    mapper_xml = builtin_file('mapper/BoardMapper.xml', 'egovframework.demo.board', schema)
    list_jsp = builtin_file('jsp/boardList.jsp', 'egovframework.demo.board', schema)

    assert 'selectBoardList(Map<String, Object> params)' in service_java
    assert 'selectBoardList(Map<String, Object> params)' in service_impl_java
    assert 'selectBoardList(new LinkedHashMap<>())' in service_impl_java
    assert 'List<BoardVO> selectBoardList(Map<String, Object> params);' in mapper_java
    assert '@RequestParam Map<String, String> requestParams' in controller_java
    assert 'selectBoardList(params)' in controller_java

    assert '<select id="selectBoardList" parameterType="map"' in mapper_xml
    assert 'title LIKE CONCAT' in mapper_xml
    assert 'content LIKE CONCAT' in mapper_xml
    assert 'writer_id = #{writerId}' in mapper_xml
    assert 'reg_dt <![CDATA[ >= ]]>' in mapper_xml
    assert 'ORDER BY reg_dt DESC' in mapper_xml

    assert 'name="keyword"' in list_jsp
    assert 'name="title"' in list_jsp
    assert 'name="content"' in list_jsp
    assert 'name="writerId"' in list_jsp
    assert 'name="regDtFrom"' in list_jsp
    assert 'name="regDtTo"' in list_jsp
    assert '<table class="autopj-table"' in list_jsp
    assert '<th>Board Id</th>' in list_jsp
    assert '<th>Title</th>' in list_jsp
    assert '<th>Content</th>' in list_jsp


def test_detail_and_form_keep_existing_values_visible_for_requested_columns():
    schema = infer_schema_from_plan({
        'tasks': [{'path': 'src/main/java/egovframework/demo/board/web/BoardController.java'}],
        'requirements_text': '''
- 테이블명은 board
- 컬럼은 아래를 사용한다
  - board_id
  - title
  - content
  - writer_id
  - use_yn
  - reg_dt
''',
    })

    detail_jsp = builtin_file('jsp/boardDetail.jsp', 'egovframework.demo.board', schema)
    form_jsp = builtin_file('jsp/boardForm.jsp', 'egovframework.demo.board', schema)
    mapper_xml = builtin_file('mapper/BoardMapper.xml', 'egovframework.demo.board', schema)

    assert '${item.boardId}' in detail_jsp
    assert '${item.title}' in detail_jsp
    assert '${item.content}' in detail_jsp
    assert '${item.writerId}' in detail_jsp
    assert '${item.useYn}' in detail_jsp
    assert '${item.regDt}' in detail_jsp

    assert "value=\"<c:out value='${item.title}'/>\"" in form_jsp
    assert "<textarea name=\"content\" class=\"form-control\"><c:out value='${item.content}'/></textarea>" in form_jsp
    assert "value=\"<c:out value='${item.writerId}'/>\"" in form_jsp
    assert 'name="useYn"' in form_jsp
    assert 'board_id = #{boardId}' in mapper_xml
    assert '<if test="title != null and title != &quot;&quot;">title = #{title},</if>' in mapper_xml
    assert '<if test="content != null and content != &quot;&quot;">content = #{content},</if>' in mapper_xml
    assert '<if test="writerId != null">writer_id = #{writerId},</if>' in mapper_xml

<!--
담당: [통합] | 책임: 승인된 Alembic revision과 각 revision의 DB 객체를 기록한다.
구현할 기능: revision 순서, pgvector 선행 조건, 테이블·인덱스 범위를 안내한다.
완료 기준: 파일에 정의된 DDL과 대상 DB 적용을 구분한다.
-->
# Alembic revisions

## 적용 순서

| Revision | DB 객체 | 내용 |
|---|---|---|
| `20261023_01_rag_chunks` | `rag.chunks` | 768차원 벡터, 게시 상태 CHECK, collection·source 검색용 B-tree와 cosine HNSW 인덱스 |
| `20261026_01_app_accounts` | `app.users`, `app.refresh_sessions`, `app.one_time_tokens`, `app.server_checklists` | 계정, Refresh 세션, 이메일·비밀번호 재설정 증표, 계정 체크리스트 저장 |

`20261026_01_app_accounts`는 `20261023_01_rag_chunks`에 종속됩니다. `20261023_01_rag_chunks`는 `extensions` 스키마에 설치된 pgvector를 요구하며, 확장을 자동 설치하지 않습니다.

## 데이터 경계

- `rag.chunks`는 RAG의 문서 청크·임베딩·게시 상태를 저장합니다.
- `app` 테이블은 계정과 별도 동의된 서버 체크리스트를 저장합니다.
- 채팅 질문·답변 원문을 저장하는 테이블은 없습니다.
- 앱 계정 revision의 `downgrade()`는 파괴적 삭제를 막기 위해 오류를 발생시킵니다.

이 문서는 migration 파일에 선언된 DDL을 설명합니다. revision을 파일에 추가한 사실과 특정 DB에 실제 적용한 사실은 별개입니다. 운영 DB에는 승인된 실행 절차로 적용합니다.

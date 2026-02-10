"""
Java 파싱 실행 스크립트.

프로젝트의 모든 .java 파일을 파싱하여 엔티티를 추출한다.

사용법 (VSCode에서):
    1. 이 파일을 열고
    2. 우클릭 → "Run Python File in Terminal"
    또는
    3. 터미널에서: python scripts/run_parse.py
"""

import sys
from pathlib import Path

# 프로젝트 루트(d:\codebase_rag)를 Python 경로에 추가
# 이래야 "from src.parsing..." import가 동작한다
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parsing.java_parser import JavaParser
from src.parsing.extractors import EntityExtractor
from src.parsing.call_graph import CallGraph


# ── 설정 ──────────────────────────────────────────────
# 파싱할 Java 프로젝트 루트 경로
JAVA_PROJECT = Path(r"D:\pwm\ui-backend\service\recipe\src\main\java")
# ────────────────────────────────────────────────────────


def main():
    # 모든 .java 파일 수집
    java_files = sorted(JAVA_PROJECT.rglob("*.java"))
    print(f"Java 파일 수: {len(java_files)}개")
    print("=" * 60)

    parser = JavaParser()
    extractor = EntityExtractor()
    all_entities = []  # 모든 파일의 엔티티를 모은다

    # 1~2단계: 각 파일을 파싱하고 엔티티 추출
    for i, java_file in enumerate(java_files, 1):
        tree, source = parser.parse_file(java_file)
        entities = extractor.extract(tree, source, java_file)
        all_entities.extend(entities)
        print(f"[{i}/{len(java_files)}] {java_file.name} → {len(entities)}개 엔티티")

    print("=" * 60)
    print(f"총 엔티티: {len(all_entities)}개")

    # 3단계: 호출 그래프 해석 (모든 엔티티가 모인 후 수행)
    graph = CallGraph()
    graph.resolve_invocations(all_entities)
    print("호출 그래프 해석 완료")
    print()

    # 타입별 통계
    from collections import Counter
    type_counts = Counter(e.entity_type for e in all_entities)
    print("── 타입별 통계 ──")
    for entity_type, count in type_counts.most_common():
        print(f"  {entity_type:12}: {count}개")


if __name__ == "__main__":
    main()

"""
Java 소스 파일 파서 모듈.

tree-sitter와 tree-sitter-java 바인딩을 사용하여
Java 소스 코드를 AST(Abstract Syntax Tree)로 변환한다.

tree-sitter는 범용 파서 프레임워크로, 언어별 바인딩(tree-sitter-java)을 통해
Java 문법을 정확하게 파싱할 수 있다. 정규식이나 문자열 처리보다
훨씬 정확한 구조적 분석이 가능하다.

사용 예:
    parser = JavaParser()
    tree, source = parser.parse_file(Path("MyService.java"))
    # tree.root_node로 AST 순회 가능
"""

from pathlib import Path

import tree_sitter_java as tsjava
from tree_sitter import Language, Parser, Tree

# tree-sitter-java의 언어 객체를 모듈 수준에서 한 번만 초기화.
# Language()는 C로 컴파일된 Java 문법 규칙을 로드한다.
# 모듈 임포트 시 한 번 실행되므로 여러 JavaParser 인스턴스가 공유한다.
JAVA_LANGUAGE = Language(tsjava.language())


class JavaParser:
    """
    Java 소스 파일을 tree-sitter AST로 변환하는 파서.

    tree-sitter Parser는 바이트 단위로 소스를 파싱하므로,
    반환되는 source도 bytes 타입이다. 노드의 start_byte/end_byte를
    사용하여 원본 소스에서 텍스트를 추출할 수 있다.
    """

    def __init__(self):
        # Parser에 Java 언어를 바인딩.
        # 이후 parse() 호출 시 Java 문법 규칙에 따라 파싱한다.
        self.parser = Parser(JAVA_LANGUAGE)

    def parse_file(self, file_path: Path) -> tuple[Tree, bytes]:
        """
        Java 파일을 파싱하여 AST와 원본 바이트를 반환한다.

        Args:
            file_path: 파싱할 Java 파일 경로

        Returns:
            (tree, source) 튜플:
            - tree: tree-sitter AST. root_node에서 순회 시작
            - source: 원본 파일의 바이트 데이터. 노드 텍스트 추출에 사용

        Note:
            파일은 바이트 모드로 읽으므로 UTF-8, EUC-KR 등
            인코딩에 관계없이 파싱 가능 (tree-sitter는 바이트 레벨 처리)
        """
        source = file_path.read_bytes() # byte 단위로 소스 읽음
        tree = self.parser.parse(source) # AST 생성
        return tree, source

    def parse_source(self, source: bytes) -> Tree:
        """
        바이트 문자열을 직접 파싱하여 AST를 반환한다.

        테스트나 동적 소스 코드 분석에 사용된다.

        Args:
            source: Java 소스 코드의 바이트 문자열

        Returns:
            tree-sitter AST Tree 객체
        """
        return self.parser.parse(source)

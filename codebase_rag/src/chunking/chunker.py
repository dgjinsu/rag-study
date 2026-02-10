"""
청킹 모듈.

CodeEntity 리스트를 RAG 검색에 적합한 Chunk 리스트로 변환한다.

청킹 전략:
- method, constructor: 주요 청킹 단위. MAX_CHUNK_LINES 이하면 단일 청크,
  초과 시 빈 줄 기준으로 논리 블록 단위 분할.
- class, interface, enum: 필드/메서드 목록을 포함한 요약 청크 1개 생성.
- field: 단독 청크 생성 안 함 (클래스 요약에 포함됨).
"""

from __future__ import annotations

from src.models import CodeEntity, Chunk
from src.chunking.text_formatter import format_chunk_text, format_class_summary


class Chunker:
    """CodeEntity 리스트를 Chunk 리스트로 변환한다."""

    def __init__(self, max_chunk_lines: int = 60):
        self.max_chunk_lines = max_chunk_lines

    def chunk_entities(self, entities: list[CodeEntity]) -> list[Chunk]:
        """
        모든 엔티티를 청크로 변환한다.

        Args:
            entities: 호출 그래프 해석이 완료된 CodeEntity 리스트.

        Returns:
            Chunk 리스트.
        """
        chunks: list[Chunk] = []

        for entity in entities:
            if entity.entity_type == "field":
                # 필드는 클래스 요약에 포함되므로 단독 청크를 만들지 않는다
                continue

            if entity.entity_type in ("class", "interface", "enum"):
                chunk = self._chunk_class(entity, entities)
                chunks.append(chunk)

            elif entity.entity_type in ("method", "constructor"):
                method_chunks = self._chunk_method(entity)
                chunks.extend(method_chunks)

        return chunks

    def _chunk_method(self, entity: CodeEntity) -> list[Chunk]:
        """메서드/생성자를 청크로 변환. 긴 경우 분할."""
        line_count = entity.end_line - entity.start_line + 1

        if line_count <= self.max_chunk_lines:
            # 단일 청크
            chunk_text = format_chunk_text(entity)
            return [self._make_chunk(entity, chunk_text, entity.source_code, 0, 1)]

        # 긴 메서드: 분할
        return self._split_long_method(entity)

    def _chunk_class(
        self,
        entity: CodeEntity,
        all_entities: list[CodeEntity],
    ) -> Chunk:
        """클래스/인터페이스/enum을 요약 청크로 변환."""
        chunk_text = format_class_summary(entity, all_entities)
        return self._make_chunk(entity, chunk_text, entity.source_code, 0, 1)

    def _split_long_method(self, entity: CodeEntity) -> list[Chunk]:
        """
        긴 메서드를 논리 블록 단위로 분할한다.

        분할 전략:
        1. 빈 줄을 기준으로 논리 블록 분할
        2. 블록이 여전히 길면 max_chunk_lines에서 강제 분할
        3. 각 파트에 메서드 시그니처를 헤더로 첨부
        """
        source_lines = entity.source_code.split("\n")
        signature = self._extract_signature(source_lines)

        # 본문 라인 (시그니처 이후)
        body_start = len(signature.split("\n"))
        body_lines = source_lines[body_start:]

        # 빈 줄 기준으로 논리 블록 분할
        blocks = self._split_by_blank_lines(body_lines)

        # 블록들을 max_chunk_lines 이내로 묶기
        part_sources: list[str] = []
        current_lines: list[str] = []
        current_count = 0
        sig_lines = len(signature.split("\n"))

        for block in blocks:
            block_len = len(block)

            # 현재 파트에 이 블록을 추가하면 초과하는 경우
            if current_count + block_len > self.max_chunk_lines - sig_lines and current_lines:
                part_sources.append("\n".join(current_lines))
                current_lines = []
                current_count = 0

            # 블록 자체가 max보다 긴 경우 강제 분할
            if block_len > self.max_chunk_lines - sig_lines:
                for i in range(0, block_len, self.max_chunk_lines - sig_lines):
                    forced_chunk = block[i : i + self.max_chunk_lines - sig_lines]
                    part_sources.append("\n".join(forced_chunk))
            else:
                current_lines.extend(block)
                current_count += block_len

        # 남은 라인
        if current_lines:
            part_sources.append("\n".join(current_lines))

        # 비어있는 파트가 없도록 처리
        if not part_sources:
            chunk_text = format_chunk_text(entity)
            return [self._make_chunk(entity, chunk_text, entity.source_code, 0, 1)]

        total_parts = len(part_sources)
        chunks: list[Chunk] = []

        for i, part_body in enumerate(part_sources):
            # 각 파트에 시그니처 헤더 첨부
            part_source = f"{signature}\n    // ... (part {i + 1}/{total_parts})\n{part_body}"
            chunk_text = format_chunk_text(entity, part_source=part_source)
            chunk = self._make_chunk(entity, chunk_text, part_source, i, total_parts)
            chunks.append(chunk)

        return chunks

    def _make_chunk(
        self,
        entity: CodeEntity,
        chunk_text: str,
        source_code: str,
        part_index: int,
        total_parts: int,
    ) -> Chunk:
        """CodeEntity와 포맷팅된 텍스트로부터 Chunk 객체를 생성."""
        return Chunk(
            chunk_id=self._make_chunk_id(entity.qualified_name, part_index),
            source_entity_id=entity.qualified_name,
            chunk_text=chunk_text,
            source_code=source_code,
            file_path=entity.file_path,
            start_line=entity.start_line,
            end_line=entity.end_line,
            entity_type=entity.entity_type,
            name=entity.name,
            qualified_name=entity.qualified_name,
            class_name=entity.class_name,
            package_name=entity.package_name,
            modifiers=entity.modifiers,
            parameters=entity.parameters,
            return_type=entity.return_type,
            annotations=entity.annotations,
            javadoc=entity.javadoc,
            calls=entity.calls,
            called_by=entity.called_by,
            part_index=part_index,
            total_parts=total_parts,
        )

    @staticmethod
    def _make_chunk_id(qualified_name: str, part_index: int) -> str:
        """chunk_id 생성. ChromaDB 호환되도록 특수문자를 치환."""
        # ChromaDB ID는 대부분의 문자를 허용하지만, 안전하게 처리
        safe_name = qualified_name.replace(" ", "_")
        return f"{safe_name}#{part_index}"

    @staticmethod
    def _extract_signature(source_lines: list[str]) -> str:
        """
        메서드 소스에서 시그니처 부분만 추출한다.

        여는 중괄호 '{'가 나오는 줄까지를 시그니처로 간주한다.
        """
        sig_lines: list[str] = []
        for line in source_lines:
            sig_lines.append(line)
            if "{" in line:
                break
        return "\n".join(sig_lines)

    @staticmethod
    def _split_by_blank_lines(lines: list[str]) -> list[list[str]]:
        """빈 줄을 기준으로 라인을 논리 블록으로 분할한다."""
        blocks: list[list[str]] = []
        current_block: list[str] = []

        for line in lines:
            if line.strip() == "":
                if current_block:
                    blocks.append(current_block)
                    current_block = []
            else:
                current_block.append(line)

        if current_block:
            blocks.append(current_block)

        return blocks

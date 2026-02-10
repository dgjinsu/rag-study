"""Kubernetes 한국어 문서 다운로드 스크립트.

GitHub의 kubernetes/website 리포에서 content/ko/docs/ 폴더의 마크다운 파일을 다운로드한다.
git sparse-checkout을 사용하여 필요한 폴더만 가져온다.
"""

import shutil
import subprocess
import sys
from pathlib import Path

REPO_URL = "https://github.com/kubernetes/website.git"
SPARSE_PATH = "content/ko/docs"
CLONE_DIR = Path("_temp_k8s_website")
OUTPUT_DIR = Path("docs/k8s-ko")


def download_k8s_docs() -> None:
    # 이미 문서가 있으면 스킵
    if OUTPUT_DIR.exists() and any(OUTPUT_DIR.rglob("*.md")):
        md_count = len(list(OUTPUT_DIR.rglob("*.md")))
        print(f"[SKIP] 이미 {md_count}개의 마크다운 파일이 존재합니다: {OUTPUT_DIR}")
        print("       다시 다운로드하려면 해당 폴더를 삭제하세요.")
        return

    # git 확인
    if not shutil.which("git"):
        print("[ERROR] git이 설치되어 있지 않습니다.")
        sys.exit(1)

    # 임시 디렉토리 정리
    if CLONE_DIR.exists():
        shutil.rmtree(CLONE_DIR)

    print(f"[1/4] kubernetes/website 리포를 sparse-checkout으로 클론합니다...")
    subprocess.run(
        [
            "git", "clone",
            "--depth", "1",
            "--filter=blob:none",
            "--sparse",
            REPO_URL,
            str(CLONE_DIR),
        ],
        check=True,
    )

    print(f"[2/4] {SPARSE_PATH} 폴더만 체크아웃합니다...")
    subprocess.run(
        ["git", "sparse-checkout", "set", SPARSE_PATH],
        cwd=str(CLONE_DIR),
        check=True,
    )

    # 문서 복사
    source_dir = CLONE_DIR / SPARSE_PATH
    if not source_dir.exists():
        print(f"[ERROR] 소스 디렉토리를 찾을 수 없습니다: {source_dir}")
        sys.exit(1)

    print(f"[3/4] 문서를 {OUTPUT_DIR}로 복사합니다...")
    OUTPUT_DIR.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    shutil.copytree(source_dir, OUTPUT_DIR)

    # 임시 디렉토리 삭제
    print("[4/4] 임시 파일을 정리합니다...")
    shutil.rmtree(CLONE_DIR)

    # 결과 출력
    md_files = list(OUTPUT_DIR.rglob("*.md"))
    print(f"\n다운로드 완료!")
    print(f"  경로: {OUTPUT_DIR.resolve()}")
    print(f"  마크다운 파일 수: {len(md_files)}")


if __name__ == "__main__":
    download_k8s_docs()

#!/bin/bash
# 빠른 로컬 개발 셋업 스크립트
# Usage: bash scripts/setup.sh

set -e

echo "=== 미국사업팀 매출/손익 관리 시스템 셋업 ==="

# 가상환경 생성
if [ ! -d "venv" ]; then
    echo ">>> Python 가상환경 생성..."
    python3 -m venv venv
fi

echo ">>> 가상환경 활성화..."
source venv/bin/activate

echo ">>> 패키지 설치..."
pip install -r requirements.txt

echo ">>> DB 마이그레이션..."
python manage.py makemigrations sales
python manage.py migrate

echo ">>> 정적 파일 수집..."
python manage.py collectstatic --noinput

echo ""
echo "=== 셋업 완료! ==="
echo ""
echo "서버 시작: python manage.py runserver"
echo "데이터 임포트: python manage.py import_excel path/to/file.xlsx"
echo "관리자 계정 생성: python manage.py createsuperuser"
echo ""
echo "Docker로 시작하려면: docker-compose up --build"

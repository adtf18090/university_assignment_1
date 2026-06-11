import pytest
from stock_dashboard.utils import get_currency_symbol, safe_float
from stock_dashboard.fetcher_yfinance import YFinanceFetcher

def test_get_currency_symbol_korea():
    """한국 주식 통화 기호 테스트"""
    assert get_currency_symbol("005930.KS") == "₩"
    assert get_currency_symbol("035720.KQ") == "₩"

def test_get_currency_symbol_us():
    """미국 주식 통화 기호 테스트"""
    assert get_currency_symbol("AAPL") == "$"
    assert get_currency_symbol("TSLA") == "$"

def test_safe_float_normal():
    """정상적인 float 변환 테스트"""
    assert safe_float("123.45") == 123.45
    assert safe_float(100) == 100.0

def test_safe_float_edge():
    """잘못된 입력값에 대한 엣지 케이스 테스트"""
    assert safe_float("abc", default=-1.0) == -1.0
    assert safe_float(None, default=0.0) == 0.0

def test_yfinance_fetcher_init():
    """클래스 초기화 및 대문자 변환 테스트"""
    fetcher = YFinanceFetcher("aapl")
    assert fetcher.ticker == "AAPL"

def test_yfinance_fetch_basic_info_normal():
    """정상 종목의 기본 정보 수집 테스트"""
    fetcher = YFinanceFetcher("AAPL")
    info = fetcher.fetch_basic_info()
    assert "price" in info
    assert "change_pct" in info
    assert info["price"] > 0

def test_yfinance_fetch_basic_info_edge():
    """존재하지 않는 종목 엣지 케이스 테스트"""
    fetcher = YFinanceFetcher("INVALID_TICKER_123")
    info = fetcher.fetch_basic_info()
    assert info["price"] == 0.0

def test_yfinance_fetch_news():
    """뉴스 데이터 포맷 테스트"""
    fetcher = YFinanceFetcher("MSFT")
    news = fetcher.fetch_news()
    assert isinstance(news, list)
    if len(news) > 0:
        assert "title" in news[0]
import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import calendar
import os


class HouseholdAccount:
    """가계부 관리 클래스 (Pandas 기반 - 20일 고정 테이블)"""

    CSV_FILENAME = 'day_money.csv'
    SETTING_FILENAME = 'setting.txt'
    MAX_DAYS = 20  # 최대 저장 일수

    def __init__(self, nestegg: int = 0, base_day: int = 25, base_money: int = 500000):
        """초기화"""
        # ✅ 설정 파일에서 기준일, 기준 금액, nestegg 로드
        loaded_settings = self.load_settings_from_file()

        if loaded_settings['base_day'] is not None:
            self.base_day = loaded_settings['base_day']
        else:
            self.base_day = base_day

        if loaded_settings['base_money'] is not None:
            self.base_money = loaded_settings['base_money']
        else:
            self.base_money = base_money

        # ✅ nestegg를 설정 파일에서 로드
        if loaded_settings['nestegg'] is not None:
            self.nestegg = loaded_settings['nestegg']
        else:
            self.nestegg = nestegg if nestegg >= 0 else 0

        # 설정이 없었다면 기본값을 파일에 저장
        if loaded_settings['base_day'] is None or loaded_settings['base_money'] is None or loaded_settings[
            'nestegg'] is None:
            self.save_settings_to_file()

        # 입력 속성
        self.dayspendmoney = 0
        self.dayearnmoney = 0

        # 날짜 관련 속성
        self.real_today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self.current_date = self.real_today

        self.day = self.current_date.day
        self.month = self.current_date.month
        self.year = self.current_date.year
        self.monthday = calendar.monthrange(self.year, self.month)[1]

        # ✅ DataFrame 초기화 (월, 일, 지출-수입, existmoney, base_income_added)
        self.df = None
        self.load_data_from_csv()

        # 20일치 테이블 초기화 (실제 오늘 날짜 기준)
        self._ensure_20_days_table()

        # ✅ 기준일 자동 수입 추가 체크
        self._check_and_add_base_day_income()

        # ✅ 전체 잔고 재계산
        self.recalculate_all_balances()

        # 현재 날짜의 잔고 로드
        self.existmoney = self.get_current_date_balance()

        # 계산 속성
        self.meanmoney = 0
        self.purposemoney = 0
        self.gap = 0
        self.yesdaymoney = 0

        # 초기 계산
        self.calculate_values()

    def get_actual_base_day(self, year, month):
        """
        특정 년/월의 유효 기준일 계산

        Args:
            year: 연도
            month: 월

        Returns:
            actual_base_day: 해당 월의 실제 기준일 (1~31)
        """
        days_in_month = calendar.monthrange(year, month)[1]
        actual_base_day = min(self.base_day, days_in_month)
        return actual_base_day

    def load_settings_from_file(self) -> dict:
        """✅ setting.txt 파일에서 기준일, 기준 금액, nestegg 불러오기"""
        settings = {'base_day': None, 'base_money': None, 'nestegg': None}

        if os.path.exists(self.SETTING_FILENAME):
            try:
                with open(self.SETTING_FILENAME, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                    if len(lines) >= 1:
                        base_day = int(lines[0].strip())
                        if 1 <= base_day <= 31:
                            settings['base_day'] = base_day

                    if len(lines) >= 2:
                        base_money = int(lines[1].strip())
                        if base_money >= 0:
                            settings['base_money'] = base_money

                    # ✅ nestegg 로드 (3번째 줄)
                    if len(lines) >= 3:
                        nestegg = int(lines[2].strip())
                        if nestegg >= 0:
                            settings['nestegg'] = nestegg

            except Exception as e:
                print(f"설정 파일 로드 오류: {e}")

        return settings

    def save_settings_to_file(self):
        """✅ 기준일, 기준 금액, nestegg를 setting.txt 파일에 저장"""
        try:
            with open(self.SETTING_FILENAME, 'w', encoding='utf-8') as f:
                f.write(f"{self.base_day}\n")
                f.write(f"{self.base_money}\n")
                f.write(f"{self.nestegg}\n")
        except Exception as e:
            print(f"설정 파일 저장 오류: {e}")

    def _ensure_20_days_table(self):
        """✅ 20일치 테이블 보장 (base_income_added 열 추가)"""
        dates = []
        for i in range(self.MAX_DAYS - 1, -1, -1):
            date = self.real_today - timedelta(days=i)
            dates.append({
                '월': date.month,
                '일': date.day,
                '지출-수입': 0,
                'existmoney': 0,
                'base_income_added': 0  # ✅ 기준금 지급 여부 (0: 미지급, 1: 지급)
            })

        new_df = pd.DataFrame(dates)

        if self.df is None or self.df.empty:
            self.df = new_df
        else:
            for idx, row in new_df.iterrows():
                month = row['월']
                day = row['일']

                existing = self.df[
                    (self.df['월'] == month) & (self.df['일'] == day)
                    ]

                if existing.empty:
                    # ✅ 새로운 날짜 추가 시
                    if idx > 0:
                        # 이전 행의 existmoney 기준으로 계산
                        prev_balance = int(new_df.at[idx - 1, 'existmoney'])
                        new_df.at[idx, 'existmoney'] = prev_balance - int(new_df.at[idx, '지출-수입'])
                    else:
                        # 첫 번째 행은 기존 값 유지 또는 0
                        if not self.df.empty:
                            new_df.at[idx, 'existmoney'] = self.df.iloc[0][
                                'existmoney'] if 'existmoney' in self.df.columns else 0
                        else:
                            new_df.at[idx, 'existmoney'] = 0

                    new_df.at[idx, '지출-수입'] = 0
                    new_df.at[idx, 'base_income_added'] = 0
                else:
                    new_df.at[idx, '지출-수입'] = existing.iloc[0]['지출-수입']

                    if 'existmoney' in existing.columns:
                        new_df.at[idx, 'existmoney'] = existing.iloc[0]['existmoney']
                    else:
                        new_df.at[idx, 'existmoney'] = 0

                    # ✅ base_income_added 값 유지
                    if 'base_income_added' in existing.columns:
                        new_df.at[idx, 'base_income_added'] = existing.iloc[0]['base_income_added']
                    else:
                        new_df.at[idx, 'base_income_added'] = 0

            self.df = new_df

    def _check_and_add_base_day_income(self):
        """✅ 20일 범위 내의 모든 기준일에 기준액 자동 추가 (유효 기준일 로직 적용)"""
        if self.df is None or self.df.empty:
            return

        # 20일 범위 내의 모든 기준일 찾기
        for idx, row in self.df.iterrows():
            month = int(row['월'])
            day = int(row['일'])
            base_income_added = int(row['base_income_added'])

            # ✅ 해당 월의 유효 기준일 계산
            # 년도는 DataFrame에 없으므로 현재 년도 사용 (20일 범위이므로 문제없음)
            year = self.real_today.year
            actual_base_day = self.get_actual_base_day(year, month)

            # ✅ 유효 기준일이고 아직 기준금이 추가되지 않았을 때만
            if day == actual_base_day and base_income_added == 0:
                # 기준액 추가 (수입이므로 음수)
                current_spend_earn = int(row['지출-수입'])
                self.df.at[idx, '지출-수입'] = current_spend_earn - self.base_money

                # ✅ 기준금 지급 플래그를 1로 설정
                self.df.at[idx, 'base_income_added'] = 1

                print(f"✅ {month}월 {day}일 (기준일)에 {self.base_money:,}원 자동 추가")

    def recalculate_all_balances(self):
        """
        ✅ DataFrame 전체의 잔고를 순차적으로 재계산
        첫 번째 행(20일 전)의 existmoney는 재계산하지 않음 (CSV 값 유지)
        두 번째 행부터 순차적으로 계산
        """
        if self.df is None or len(self.df) == 0:
            return

        # ✅ 두 번째 행부터 순차 계산
        for i in range(1, len(self.df)):
            prev_balance = int(self.df.at[i - 1, 'existmoney'])
            current_spend_earn = int(self.df.at[i, '지출-수입'])
            self.df.at[i, 'existmoney'] = prev_balance - current_spend_earn

    def get_current_date_balance(self) -> int:
        """✅ 현재 조회 중인 날짜의 잔고를 DataFrame에서 가져오기"""
        if self.df is None or self.df.empty:
            return 0

        day_data = self.df[
            (self.df['월'] == self.month) & (self.df['일'] == self.day)
            ]

        if not day_data.empty:
            return int(day_data.iloc[-1]['existmoney'])
        else:
            return 0

    def load_data_from_csv(self):
        """✅ CSV 파일에서 데이터 불러오기 (base_income_added 열 추가)"""
        if os.path.exists(self.CSV_FILENAME):
            try:
                df = pd.read_csv(self.CSV_FILENAME, encoding='utf-8-sig')

                if '월' in df.columns and '일' in df.columns and '지출-수입' in df.columns:
                    # ✅ nestegg 컬럼이 있으면 제거
                    if 'nestegg' in df.columns:
                        df = df.drop(columns=['nestegg'])

                    if 'existmoney' not in df.columns:
                        df['existmoney'] = 0

                    # ✅ base_income_added 열이 없으면 추가
                    if 'base_income_added' not in df.columns:
                        df['base_income_added'] = 0

                    self.df = df
                else:
                    self._create_new_dataframe()

            except Exception as e:
                print(f"CSV 로드 오류: {e}")
                self._create_new_dataframe()
        else:
            self._create_new_dataframe()

    def _create_new_dataframe(self):
        """✅ 새로운 DataFrame 생성 (base_income_added 열 포함)"""
        self.df = pd.DataFrame(columns=['월', '일', '지출-수입', 'existmoney', 'base_income_added'])

    def save_data_to_csv(self):
        """✅ DataFrame을 CSV 파일에 저장 (base_income_added 포함)"""
        try:
            # nestegg 컬럼이 있으면 제거 후 저장
            df_to_save = self.df.copy()
            if 'nestegg' in df_to_save.columns:
                df_to_save = df_to_save.drop(columns=['nestegg'])

            df_to_save.to_csv(self.CSV_FILENAME, index=False, encoding='utf-8-sig')
        except Exception as e:
            print(f"CSV 저장 오류: {e}")

    def is_real_today(self) -> bool:
        """현재 화면 날짜가 실제 오늘인지 확인"""
        return self.current_date.date() == self.real_today.date()

    def get_day_value(self, month: int, day: int) -> dict:
        """✅ 특정 날짜의 지출-수입과 잔고 값을 딕셔너리로 반환"""
        result = {
            '지출-수입': 0,
            'existmoney': 0
        }

        if self.df is None or self.df.empty:
            return result

        day_data = self.df[
            (self.df['월'] == month) & (self.df['일'] == day)
            ]

        if not day_data.empty:
            result['지출-수입'] = int(day_data.iloc[-1]['지출-수입'])
            if 'existmoney' in day_data.columns:
                result['existmoney'] = int(day_data.iloc[-1]['existmoney'])

        return result

    def get_yesterday_value(self) -> int:
        """어제의 지출-수입 값을 DataFrame에서 조회"""
        if self.df is None or self.df.empty:
            return 0

        current_data = self.df[
            (self.df['월'] == self.month) & (self.df['일'] == self.day)
            ]

        if not current_data.empty:
            current_idx = current_data.index[0]

            if current_idx > 0:
                return int(self.df.iloc[current_idx - 1]['지출-수입'])

        return 0

    def update_date_info(self):
        """현재 날짜 정보 업데이트"""
        self.day = self.current_date.day
        self.month = self.current_date.month
        self.year = self.current_date.year
        self.monthday = calendar.monthrange(self.year, self.month)[1]

    def calculate_values(self):
        """계산 속성들을 갱신 (유효 기준일 로직 적용)"""
        # ✅ 이번 달의 유효 기준일
        actual_base_day_this_month = self.get_actual_base_day(self.year, self.month)

        if self.day < actual_base_day_this_month:
            # 이번 달 기준일이 아직 안 지남
            remaining_days = actual_base_day_this_month - self.day
        else:
            # 이번 달 기준일이 지남 → 다음 달 기준일까지
            next_month = self.month + 1
            next_year = self.year
            if next_month > 12:
                next_month = 1
                next_year += 1

            # ✅ 다음 달의 유효 기준일
            actual_base_day_next_month = self.get_actual_base_day(next_year, next_month)

            # 이번 달 남은 일수 + 다음 달 기준일까지
            days_in_current_month = calendar.monthrange(self.year, self.month)[1]
            remaining_days = (days_in_current_month - self.day) + actual_base_day_next_month

        # ✅ meanmoney 계산: (existmoney - nestegg) // remaining_days
        if remaining_days > 0:
            self.meanmoney = (self.existmoney - self.nestegg) // remaining_days
        else:
            self.meanmoney = self.existmoney - self.nestegg

        # purposemoney 계산
        self.purposemoney = (self.base_money - self.nestegg) // self.monthday

        if self.purposemoney != 0:
            self.gap = (self.purposemoney - self.meanmoney) * 100 // self.purposemoney
        else:
            self.gap = 0

        self.yesdaymoney = self.get_yesterday_value()

    def update(self, dayspendmoney: int = 0, dayearnmoney: int = 0, nestegg: int = 0):
        """✅ 입력값을 받아 가계부 갱신 (nestegg는 setting.txt에 저장)"""
        self.dayspendmoney = dayspendmoney
        self.dayearnmoney = dayearnmoney

        # ✅ nestegg 업데이트 및 setting.txt에 저장
        self.nestegg = nestegg if nestegg >= 0 else 0
        self.save_settings_to_file()

        spend_earn_diff = dayspendmoney - dayearnmoney

        mask = (self.df['월'] == self.month) & (self.df['일'] == self.day)
        matching_rows = self.df[mask]

        if not matching_rows.empty:
            idx = matching_rows.index[0]

            # ✅ 지출-수입 업데이트 (기존 값에 추가)
            self.df.at[idx, '지출-수입'] = int(self.df.at[idx, '지출-수입']) + spend_earn_diff

        # ✅ 전체 잔고 재계산 (핵심!)
        self.recalculate_all_balances()

        # ✅ 현재 날짜의 잔고를 self.existmoney에 로드
        self.existmoney = self.get_current_date_balance()

        # 계산값 갱신
        self.calculate_values()

        # CSV 저장
        self.save_data_to_csv()

        return True

    def next_day(self):
        """다음 날로 이동"""
        if self.current_date.date() >= self.real_today.date():
            return False

        self.current_date += timedelta(days=1)
        self.update_date_info()

        if self.is_real_today():
            self._ensure_20_days_table()
            # ✅ 기준일 체크
            self._check_and_add_base_day_income()
            self.recalculate_all_balances()

        self.dayspendmoney = 0
        self.dayearnmoney = 0

        # ✅ 이동한 날짜의 잔고 로드
        self.existmoney = self.get_current_date_balance()

        self.calculate_values()

        if self.is_real_today():
            self.save_data_to_csv()

        return True

    def prev_day(self):
        """✅ 이전 날로 이동 (19일 전까지만 허용, 20일 전은 접근 불가)"""
        # ✅ 19일 전 날짜 계산 (20일 전은 접근 불가)
        oldest_accessible_date = self.real_today - timedelta(days=self.MAX_DAYS - 2)

        # ✅ 이동하려는 날짜가 19일 전보다 이전이면 이동 불가
        target_date = self.current_date - timedelta(days=1)
        if target_date.date() < oldest_accessible_date.date():
            return False

        self.current_date = target_date
        self.update_date_info()

        self.dayspendmoney = 0
        self.dayearnmoney = 0

        # ✅ 이동한 날짜의 잔고 로드
        self.existmoney = self.get_current_date_balance()

        self.calculate_values()

        return True

    def is_base_income_added(self) -> bool:
        """✅ 현재 날짜에 기준금이 추가되었는지 확인"""
        if self.df is None or self.df.empty:
            return False

        day_data = self.df[
            (self.df['월'] == self.month) & (self.df['일'] == self.day)
            ]

        if not day_data.empty and 'base_income_added' in day_data.columns:
            return int(day_data.iloc[-1]['base_income_added']) == 1

        return False

    def get_output(self) -> tuple:
        """출력값 5개 반환"""
        day_data = self.get_day_value(self.month, self.day)
        output1 = day_data['지출-수입']
        output2 = self.meanmoney
        output3 = self.purposemoney
        output4 = self.nestegg
        output5 = output1 - self.yesdaymoney

        return output1, output2, output3, output4, output5


def initialize_session_state():
    """세션 상태 초기화"""
    if 'account' not in st.session_state:
        st.session_state.account = HouseholdAccount()
    if 'message' not in st.session_state:
        st.session_state.message = None
    if 'base_day' not in st.session_state:
        st.session_state.base_day = st.session_state.account.base_day
    if 'base_money' not in st.session_state:
        st.session_state.base_money = st.session_state.account.base_money
    if 'nestegg' not in st.session_state:
        st.session_state.nestegg = st.session_state.account.nestegg


def move_to_prev_day():
    """✅ 이전 날로 이동 (19일 전까지만, 20일 전은 접근 불가)"""
    success = st.session_state.account.prev_day()
    if success:
        st.session_state.message = f"← {st.session_state.account.year}년 {st.session_state.account.month}월 {st.session_state.account.day}일로 이동했습니다."
    else:
        st.session_state.message = "❌ 19일 이전 데이터는 조회할 수 없습니다!"


def move_to_next_day():
    """다음 날로 이동"""
    success = st.session_state.account.next_day()
    if not success:
        st.session_state.message = "❌ 미래 날짜로는 이동할 수 없습니다!"
    else:
        st.session_state.message = f"→ {st.session_state.account.year}년 {st.session_state.account.month}월 {st.session_state.account.day}일로 이동했습니다."


def get_gap_status(gap: int) -> tuple:
    """GAP 값에 따른 상태와 이모지 반환"""
    if gap <= 0:
        return "🟢 안전", "green"
    elif 0 < gap <= 10:
        return "🟡 적정", "orange"
    elif 10 < gap < 20:
        return "🟠 위험", "red"
    else:
        return "🔴 심각", "red"


def main():
    """메인 Streamlit 앱"""
    st.set_page_config(
        page_title="가계부",
        layout="wide"
    )

    initialize_session_state()
    account = st.session_state.account

    # SIDEBAR
    with st.sidebar:
        st.markdown("### 📅 실제 오늘")
        st.markdown(f"**{account.real_today.year}년 {account.real_today.month}월 {account.real_today.day}일**")

        st.divider()

        st.markdown("### 🔍 조회 중인 날짜")
        if not account.is_real_today():
            st.markdown(f"**{account.year}년 {account.month}월 {account.day}일** (과거)")
        else:
            st.markdown(f"**{account.year}년 {account.month}월 {account.day}일**")

        if account.day == account.base_day:
            if account.is_base_income_added():
                st.markdown("🎯 **오늘은 기준일입니다! (기준금 지급 완료)**")
            else:
                st.markdown("🎯 **오늘은 기준일입니다!**")

        col1, col2 = st.columns(2)
        with col1:
            st.button("◀", on_click=move_to_prev_day, use_container_width=True, key="prev_day_btn")
        with col2:
            st.button("▶", on_click=move_to_next_day, use_container_width=True, key="next_day_btn")

        if st.session_state.message:
            if "❌" in st.session_state.message:
                st.error(st.session_state.message)
            else:
                st.success(st.session_state.message)
            st.session_state.message = None

        st.divider()

        output5 = account.get_output()[4]

        if output5 > 0:
            st.markdown(f"## 어제보다 {output5:,}원 더 쓰셨습니다!")
        elif output5 < 0:
            st.markdown(f"## 어제보다 {abs(output5):,}원 덜 쓰셨습니다!")
        else:
            st.markdown(f"## 어제와 동일한 금액을 쓰셨습니다!")

        st.markdown("<br>", unsafe_allow_html=True)

        if not account.is_real_today():
            st.markdown(f'### 해당 날짜 잔고: {account.existmoney:,}원')
        else:
            st.markdown(f'### 현재 잔고: {account.existmoney:,}원')

        gap_status, gap_color = get_gap_status(account.gap)
        st.markdown(f"### {gap_status}")

        st.divider()

        st.markdown("### ⚙️ 설정")

        base_day = st.number_input(
            "월 기준일 (1~31)",
            min_value=1,
            max_value=31,
            value=st.session_state.base_day,
            step=1,
            help="한 달의 시작 기준일을 설정합니다."
        )

        base_money = st.number_input(
            "월 기준 금액 (원)",
            min_value=0,
            value=st.session_state.base_money,
            step=10000,
            help="기준일에 자동으로 추가될 금액입니다."
        )

        nestegg_setting = st.number_input(
            "비상금 (원)",
            min_value=0,
            value=st.session_state.nestegg,
            step=10000,
            help="비상금을 설정합니다. (전체 잔고 중 지출하지 않을 금액입니다.)"
        )

        settings_changed = False
        base_day_changed = False
        base_money_changed = False

        if base_day != st.session_state.base_day:
            st.session_state.base_day = base_day
            account.base_day = base_day
            settings_changed = True
            base_day_changed = True

        if base_money != st.session_state.base_money:
            st.session_state.base_money = base_money
            account.base_money = base_money
            settings_changed = True
            base_money_changed = True

        if nestegg_setting != st.session_state.nestegg:
            st.session_state.nestegg = nestegg_setting
            account.nestegg = nestegg_setting
            settings_changed = True

        if settings_changed:
            account.save_settings_to_file()

            if base_day_changed or base_money_changed:
                account.df['base_income_added'] = 0
                account._check_and_add_base_day_income()
                account.recalculate_all_balances()
                account.existmoney = account.get_current_date_balance()
                account.save_data_to_csv()

            account.calculate_values()
            st.success(f"✅ 설정이 저장되었습니다!\n- 기준일: {base_day}일\n- 기준 금액: {base_money:,}원\n- 비상금: {nestegg_setting:,}원")

            if base_day_changed or base_money_changed:
                st.info(f"💡 기준일({base_day}일)에 {base_money:,}원이 자동으로 추가되었습니다.")
                st.rerun()

    # MAIN CONTENT
    st.markdown("<h1 style='text-align: center;'>가계부 프로그램</h1>", unsafe_allow_html=True)
    st.divider()

    if not account.is_real_today():
        st.info(f"📌 과거 날짜({account.year}년 {account.month}월 {account.day}일) 데이터를 수정 중입니다.")

    if account.day == account.base_day:
        if account.is_base_income_added():
            st.success(f"🎯 오늘은 기준일입니다! {account.base_money:,}원이 자동으로 추가되었습니다.")
        else:
            st.warning(f"⚠️ 아직 기준금이 추가되지 않았습니다.")

    with st.form(key="input_form", clear_on_submit=False):
        col1, col2, col3 = st.columns([3, 3, 1])

        with col1:
            dayspend = st.number_input(
                "지출 금액",
                min_value=0,
                value=0,
                step=1000,
                key="dayspend_input"
            )

        with col2:
            dayearn = st.number_input(
                "받은 금액",
                min_value=0,
                value=0,
                step=1000,
                key="dayearn_input"
            )

        with col3:
            st.markdown("<div style='margin-top: 32px;'></div>", unsafe_allow_html=True)
            submit_button = st.form_submit_button("입력", use_container_width=True, type="primary")

    if submit_button:
        success = account.update(dayspend, dayearn, account.nestegg)
        if success:
            st.success(f"지출 {dayspend:,}원, 수입 {dayearn:,}원이 입력되었습니다!")
            st.rerun()
        else:
            st.error("❌ 데이터 입력에 실패했습니다!")

    st.divider()

    output1, output2, output3, output4, output5 = account.get_output()

    st.markdown("""
        <style>
        .stTabs [data-baseweb="tab-list"] {
            gap: 0px;
        }
        .stTabs [data-baseweb="tab"] {
            flex: 1;
            white-space: pre-wrap;
            justify-content: center;
        }
        </style>
        """, unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs([
        "현재 총 지출금",
        "하루 지출 가능 금액",
        "현재 목표 지출금",
        "현재 비상금"
    ])

    with tab1:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"### 현재 총 지출금")
        st.markdown(f"## {output1:,}원")

    with tab2:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"### 하루 지출 가능 금액")
        st.markdown(f"## {output2:,}원")

    with tab3:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"### 현재 목표 지출금")
        st.markdown(f"## {output3:,}원")

    with tab4:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"### 현재 비상금")
        st.markdown(f"## {output4:,}원")

    # ✅ GAP 상태가 '심각'일 때 경고 메시지 표시
    gap_status, gap_color = get_gap_status(account.gap)
    if gap_status == "🔴 심각":
        st.divider()
        st.error("⚠️ **비상금을 줄여야 합니다!**")


if __name__ == "__main__":
    main()
"""공공심야약국의 월요일 시작시각 보완과 분석용 시간표.

연구 목적은 22시~익일01시 접근성입니다. 정확히 아침 몇 시에 여는지보다
월요일에도 심야 운영을 하는지, 몇 시에 닫는지가 더 중요합니다.
그래서 지정약국에 한해 같은 약국의 화~금 공통 시작시각을 월요일 추정값으로
사용합니다. 이는 평일 운영 패턴이 월요일에도 유지된다는 가정이며 현장 확인이
아닙니다. 원본 결측, 공휴일, 종료시각을 이 가정으로 덮어쓰지 않습니다.
"""
import pandas as pd
from pharmacy_data import START, END, minute, interval, opening_state


def monday_start_for(row, is_designated):
    """원본값 우선. 지정약국+월요일 결측+화~금 4개 유효값 일치 때만 보완합니다."""
    raw = row[START[0]]
    if not pd.isna(raw) and str(raw).strip():
        return raw, False, 'api_original'
    if not is_designated:
        return raw, False, 'not_imputed_not_designated'
    weekday_minutes = [minute(row[column]) for column in START[1:5]]
    # 3일만 있거나 서로 다르면 최빈값으로 임의 대체하지 않습니다.
    if None in weekday_minutes or len(set(weekday_minutes)) != 1:
        return raw, False, 'not_imputed_no_four_day_consensus'
    value = weekday_minutes[0]
    return f'{value // 60:02d}{value % 60:02d}', True, 'estimated_from_same_pharmacy_tue_fri_consensus'


def build_monday_analysis(run, raw, master, original_hours, original_states):
    """원본 기준 파일은 유지하고 _analysis 파일에만 보완된 시간표를 만듭니다."""
    designated_ids = set(master.loc[master.public_designation_status.eq('matched_designated'), 'pharmacy_id'])
    hours = original_hours.copy()
    hours['start_effective'] = hours['start_raw']
    hours['start_imputed'] = False
    hours['start_value_source'] = 'api_original'
    audit, states = [], []
    for _, row in raw.iterrows():
        pid = row['pmcyId']
        effective, imputed, reason = monday_start_for(row, pid in designated_ids)
        schedules = [interval(effective if day == 0 else row[sc], row[ec])
                     for day, (sc, ec) in enumerate(zip(START, END))]
        if pid in designated_ids:
            audit.append({'pharmacy_id': pid, 'name': row['pmcyNm'], 'monday_start_raw': row[START[0]],
                'monday_start_effective': effective, 'monday_start_imputed': imputed,
                'imputation_method': reason, 'monday_end_raw': row[END[0]],
                **{day + '_start_raw': row[sc] for day, sc in zip(['tue','wed','thu','fri','sat','sun'],START[1:7])},
                'research_note': '22시~익일01시 접근성: 오전 개점시각보다 심야 운영 여부·종료시각 중요. 보완값은 추정이며 현장확인 아님.'})
        mask = hours.pharmacy_id.eq(pid) & hours.day_code.eq(1)
        hours.loc[mask, 'start_effective'] = effective
        hours.loc[mask, 'start_value_source'] = reason
        hours.loc[mask, 'start_imputed'] = imputed
        if imputed:
            parsed = schedules[0]
            hours.loc[mask, 'start_minute'] = parsed[0] if parsed else None
            hours.loc[mask, 'end_minute_unwrapped'] = parsed[1] if parsed else None
            hours.loc[mask, 'hours_status'] = 'estimated' if parsed else 'unknown'
            hours.loc[mask, 'crosses_midnight'] = parsed[1] > 1440 if parsed else None
        for day in range(7):
            for hour in (0,22,23):
                states.append({'pharmacy_id':pid,'day_code':day+1,'hour':hour,
                    'schedule_status':opening_state(schedules[day],schedules[(day-1)%7],hour*60),
                    # 월요일 당일과 화요일 전날 시간표에 보완값이 입력된 경우를 표시합니다.
                    # 이 플래그가 True라고 모든 해당 슬롯의 판정이 바뀌었다는 뜻은 아닙니다.
                    'has_imputed_schedule_input': bool(imputed and day in (0,1)),
                    'calendar_assumption':'today_and_yesterday_are_non_holidays'})
    analysis = pd.DataFrame(states)
    analysis = analysis.merge(original_states[['pharmacy_id','day_code','hour','schedule_status',
        'public_designation_status','has_notes_requires_review']].rename(columns={'schedule_status':'original_schedule_status'}),
        on=['pharmacy_id','day_code','hour'],validate='one_to_one')
    analysis['status_changed_by_imputation'] = analysis.schedule_status.ne(analysis.original_schedule_status)
    analysis['policy_schedule_conflict'] = analysis.public_designation_status.eq('matched_designated') & analysis.schedule_status.eq('closed')
    audit = pd.DataFrame(audit)
    run.save('monday_imputation_audit', audit)
    run.save('pharmacy_opening_hours_analysis', hours)
    run.save('pharmacy_night_weekly_analysis', analysis)
    run.save('designation_schedule_review_analysis', analysis[
        analysis.public_designation_status.eq('matched_designated') & analysis.schedule_status.ne('open')])
    transitions = analysis[analysis.public_designation_status.eq('matched_designated')].groupby(
        ['original_schedule_status','schedule_status']).size().rename('weekday_hour_slots').reset_index()
    run.save('monday_imputation_status_changes', transitions)
    run.quality['monday_imputation'] = {'scope':'matched_designated_pharmacies_only',
        'imputed_pharmacies':int(audit.monday_start_imputed.sum()),
        'changed_weekday_hour_slots':int(analysis.status_changed_by_imputation.sum()),
        'original_raw_preserved':True,'analysis_unknown_hours_rows':int(hours.hours_status.eq('unknown').sum()),
        'designated_policy_conflict_slots':int(analysis.policy_schedule_conflict.sum()),
        'assumption':'같은 약국의 화~금 공통 시작시각을 비공휴일 월요일에 적용. 현장확인 아님.'}

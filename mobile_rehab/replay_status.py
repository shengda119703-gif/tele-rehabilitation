"""Replay errors are not all codec failures; preserve timing omission evidence."""
def replay_ended(statuses, timing):
    for status in statuses:
        if status['status'] == 'REPLAY_PREROLL_SKIPPED':
            timing.update(skipped_leading_frames=status['skipped_frames'],
                          last_skipped_raw_time_s=status['raw_time_s'])
    error = next((s for s in statuses if s['status'] == 'ERROR'), None)
    if error:
        raise ValueError('录像读取失败：' + error.get('message', '请使用普通录像重试。'))
    if any(s['status'] == 'EOF' for s in statuses):
        return True
    if any(s['status'] in ('RELEASED', 'RELEASE_UNCONFIRMED') for s in statuses):
        raise ValueError('录像读取提前结束，请重新上传。')
    return False

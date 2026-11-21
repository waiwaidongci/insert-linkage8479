from src.constants.enums import PackState
from src.utils.time import iso


def dataset(item):
    return {'id': item.id, 'name': item.name, 'filename': item.filename, 'row_count': item.row_count,
            'checksum': item.checksum, 'author': item.author, 'created_at': iso(item.created_at)}


def run(item, detail=False):
    item_view = {'id': item.id, 'dataset_id': item.dataset_id, 'name': item.name, 'status': item.status,
                 'author': item.author, 'review': item.review, 'decision': item.decision,
                 'created_at': iso(item.created_at), 'finished_at': iso(item.finished_at),
                 'scheduled_at': iso(item.scheduled_at), 'schedule_id': item.schedule_id,
                 'has_export': bool(item.export_file), 'error': item.error}
    if detail:
        item_view.update(params=item.params, result=item.result, review_note=item.review_note)
    return item_view


def schedule(item):
    from src.domain.spec import SPEC
    return {'id': item.id, 'name': item.name, 'dataset_id': item.dataset_id, 'recipient': item.recipient,
            'next_at': iso(item.next_at), 'repeat_daily': item.repeat_daily, 'enabled': item.enabled,
            'next_report_day': item.params.get(SPEC['schedule_date_param']) if item.enabled else None}


def delivery(item):
    return {'id': item.id, 'run_id': item.run_id, 'recipient': item.recipient,
            'state': item.state, 'detail': item.detail, 'created_at': iso(item.created_at)}


def list_version(item):
    return {'version': item.version, 'run_id': item.run_id, 'entry_count': item.entry_count,
            'fingerprint': item.fingerprint, 'author': item.author, 'created_at': iso(item.created_at)}


def package(item):
    return {'seq': item.seq, 'state': item.state, 'item_count': item.item_count,
            'fingerprint': item.fingerprint, 'summary': item.summary,
            'receipt': item.receipt, 'acked_by': item.acked_by, 'acked_at': iso(item.acked_at)}


def shipment(item, packages):
    summary = {'added': 0, 'removed': 0, 'changed': 0}
    for pack in packages:
        for op, count in pack['summary'].items():
            summary[op] += count
    return {'id': item.id, 'from_version': item.from_version, 'to_version': item.to_version,
            'state': item.state, 'package_count': item.package_count,
            'acked': sum(1 for pack in packages if pack['state'] == PackState.ACKED),
            'summary': summary, 'created_at': iso(item.created_at), 'completed_at': iso(item.completed_at)}

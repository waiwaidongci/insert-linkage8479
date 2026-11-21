"""采购站点备料清单的版本生成、分包派发与回执推进。"""

from sqlalchemy import func, select
from src.constants.enums import PackState, ShipState
from src.domain import listing
from src.domain.spec import SPEC
from src.models.procure import ListVersion, Package, Shipment, SiteState
from src.models.source import Dataset
from src.services.audit import record
from src.utils.time import now

PACK_SIZE = SPEC['pack_size']


def site_state(db, site, lock=True):
    state = db.get(SiteState, site, with_for_update=lock)
    if state is None:
        state = SiteState(site=site, baseline=0)
        db.add(state)
        db.flush()
    return state


def open_shipment(db, site, lock=False):
    query = (select(Shipment).where(Shipment.site == site, Shipment.state == ShipState.OPEN)
             .order_by(Shipment.id).limit(1))
    return db.scalar(query.with_for_update() if lock else query)


def latest_version(db, lock=False):
    query = select(func.max(ListVersion.version))
    return db.scalar(query.with_for_update() if lock else query)


def version_entries(db, version):
    if version == 0:
        return []
    return db.scalar(select(ListVersion.entries).where(ListVersion.version == version))


def maybe_dispatch(db, state):
    """站点无在途发货且基线落后时生成下一批差量包；无差异直接推进基线。

    调用方须已锁定该站点行，保证每站同一时间至多一个在途发货。
    """
    latest = latest_version(db)
    if latest is None or state.baseline >= latest or open_shipment(db, state.site):
        return
    items = listing.diff_entries(version_entries(db, state.baseline), version_entries(db, latest))
    if not items:
        state.baseline = latest
        record(db, 'system', 'site.baseline', state.site, baseline=latest, packages=0)
        return
    shipment = Shipment(site=state.site, from_version=state.baseline, to_version=latest,
                        package_count=(len(items) + PACK_SIZE - 1) // PACK_SIZE)
    db.add(shipment)
    db.flush()
    for seq, pack_items in enumerate(listing.chunks(items, PACK_SIZE), start=1):
        document = listing.pack_view(state.site, shipment.from_version, latest, seq,
                                     shipment.package_count, pack_items)
        db.add(Package(shipment_id=shipment.id, seq=seq, item_count=len(pack_items),
                       fingerprint=listing.fingerprint(document), summary=listing.summarize(pack_items),
                       items=pack_items))
    record(db, 'system', 'shipment.created', shipment.id, site=state.site,
           from_version=shipment.from_version, to_version=latest,
           packages=shipment.package_count, entries=len(items))


def sign_version(db, run, actor):
    """复核签核生成清单版本，并按各站进度安排发货；站点在途时等旧包收齐。"""
    dataset = db.get(Dataset, run.dataset_id)
    entries = listing.entries_from_run(run.result, dataset.rows)
    item = ListVersion(version=(latest_version(db, lock=True) or 0) + 1, run_id=run.id,
                       entry_count=len(entries), fingerprint=listing.fingerprint(entries),
                       entries=entries, author=actor)
    db.add(item)
    db.flush()
    record(db, actor, 'version.signed', item.version, run_id=run.id, entries=len(entries))
    for site in SPEC['sites']:
        maybe_dispatch(db, site_state(db, site))
    return item


def acknowledge(db, site, seq, receipt, actor):
    """核对包号与内容指纹；收齐推进本站基线，并视情况派发下一批差量。"""
    state = site_state(db, site)
    shipment = open_shipment(db, site, lock=True)
    if shipment is None:
        raise ValueError('当前站点没有待确认的包，请刷新后核对。')
    query = select(Package).where(Package.shipment_id == shipment.id, Package.seq == seq)
    package = db.scalar(query.with_for_update())
    if package is None:
        raise ValueError('找不到该包号，请核对站点待收清单。')
    if package.state == PackState.ACKED:
        if package.receipt == receipt:
            return package, shipment, state
        raise ValueError('该包已确认，本次回执指纹与原回执不符。')
    if package.fingerprint != receipt:
        raise ValueError('回执指纹与包内容不符，请重新下载该包后再确认。')
    package.state = PackState.ACKED
    package.receipt = receipt
    package.acked_by = actor
    package.acked_at = now()
    record(db, actor, 'package.acked', package.id, site=site, shipment=shipment.id, seq=seq)
    remaining = db.scalar(select(func.count()).select_from(Package).where(
        Package.shipment_id == shipment.id, Package.state == PackState.PENDING))
    if remaining == 0:
        shipment.state = ShipState.COMPLETE
        shipment.completed_at = now()
        state.baseline = shipment.to_version
        record(db, 'system', 'shipment.completed', shipment.id, site=site, baseline=state.baseline)
        maybe_dispatch(db, state)
    return package, shipment, state

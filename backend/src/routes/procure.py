from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.config.database import connection
from src.constants.enums import Role
from src.controllers.auth import allow, current
from src.domain import listing
from src.domain.spec import SPEC
from src.models.identity import User
from src.models.procure import ListVersion, Package, SiteState
from src.schemas.requests import AckRequest
from src.services import dispatch
from src.utils import views
from src.utils.time import iso

router = APIRouter(prefix='/procure')


def require_site(site):
    if site not in SPEC['sites']:
        raise HTTPException(404, '找不到该采购站点')
    return site


def state_of(db, site):
    return db.get(SiteState, site) or SiteState(site=site, baseline=0)


def outbox_view(db, site):
    state = state_of(db, site)
    shipment = dispatch.open_shipment(db, site)
    packages = []
    if shipment:
        rows = db.scalars(select(Package).where(Package.shipment_id == shipment.id).order_by(Package.seq))
        packages = [views.package(item) for item in rows]
    return {'site': site, 'baseline': state.baseline, 'latest_version': dispatch.latest_version(db) or 0,
            'shipment': views.shipment(shipment, packages) if shipment else None, 'packages': packages}


@router.get('/versions')
def versions(db: Session = Depends(connection), actor: User = Depends(current)):
    rows = db.scalars(select(ListVersion).order_by(ListVersion.version.desc()).limit(50))
    return [views.list_version(item) for item in rows]


@router.get('/sites/{site}/outbox')
def outbox(site: str, db: Session = Depends(connection), actor: User = Depends(current)):
    return outbox_view(db, require_site(site))


@router.get('/sites/{site}/packages/{seq}')
def download(site: str, seq: int, db: Session = Depends(connection), actor: User = Depends(current)):
    require_site(site)
    shipment = dispatch.open_shipment(db, site)
    if shipment is None:
        raise HTTPException(409, '当前站点没有待收的发货')
    package = db.scalar(select(Package).where(Package.shipment_id == shipment.id, Package.seq == seq))
    if package is None:
        raise HTTPException(404, '找不到该包号，请核对站点待收清单')
    document = listing.pack_view(site, shipment.from_version, shipment.to_version,
                                 package.seq, shipment.package_count, package.items)
    if listing.fingerprint(document) != package.fingerprint:
        raise HTTPException(500, '包内容指纹校验失败，请联系管理员核查')
    return {**document, 'fingerprint': package.fingerprint, 'state': package.state}


@router.post('/sites/{site}/packages/{seq}/ack')
def ack(site: str, seq: int, body: AckRequest, db: Session = Depends(connection),
        actor: User = Depends(allow(Role.ADMIN, Role.ANALYST))):
    require_site(site)
    package, shipment, state = dispatch.acknowledge(db, site, seq, body.fingerprint, actor.username)
    db.commit()
    return {'site': site, 'seq': package.seq, 'state': package.state, 'receipt': package.receipt,
            'acked_by': package.acked_by, 'acked_at': iso(package.acked_at),
            'shipment_state': shipment.state, 'baseline': state.baseline}

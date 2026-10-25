from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aichat.core.db import get_session
from aichat.core.deps import AuthHuman, current_human
from aichat.modules.contacts.models import ContactRequest
from aichat.modules.contacts.schemas import ContactRequestIn, DecisionIn, contact_request_out, public_account_out
from aichat.modules.contacts.service import ContactsService
from aichat.modules.identity.models import Account

router = APIRouter(tags=["contacts"])


def svc(request: Request, session: AsyncSession = Depends(get_session)) -> ContactsService:
    return ContactsService(request.app.state.ctx, session)


@router.get("/accounts/by-handle")
async def by_handle(handle: str, auth: AuthHuman = Depends(current_human),
                    service: ContactsService = Depends(svc)):
    return public_account_out(await service.find_by_handle(handle))


@router.post("/contact-requests")
async def create_request(body: ContactRequestIn, auth: AuthHuman = Depends(current_human),
                         service: ContactsService = Depends(svc)):
    row = await service.request_contact(auth.account_id, body.target_account_id)
    target = await service.session.get(Account, row.target_id)
    return contact_request_out(row, target, auth.account_id)


@router.get("/contact-requests")
async def list_requests(auth: AuthHuman = Depends(current_human), service: ContactsService = Depends(svc)):
    items = []
    for row, account in await service.pending_requests_for(auth.account_id):
        items.append(contact_request_out(row, account, auth.account_id))
    return {"items": items}


@router.post("/contact-requests/{request_id}/decision")
async def decide(request_id: str, body: DecisionIn, auth: AuthHuman = Depends(current_human),
                 service: ContactsService = Depends(svc)):
    row = await service.decide_contact_request(request_id, auth.account_id, body.decision == "accept")
    account = await service.session.get(Account, row.requester_id)
    return contact_request_out(row, account, auth.account_id)


@router.get("/contacts")
async def list_contacts(auth: AuthHuman = Depends(current_human), service: ContactsService = Depends(svc)):
    return {"items": [public_account_out(a) for a in await service.list_contacts(auth.account_id)]}


@router.delete("/contacts/{account_id}")
async def remove_contact(account_id: str, auth: AuthHuman = Depends(current_human),
                         service: ContactsService = Depends(svc)):
    await service.remove_contact(auth.account_id, account_id)
    return {"removed": True}


@router.post("/contacts/{account_id}/block")
async def block(account_id: str, auth: AuthHuman = Depends(current_human),
                service: ContactsService = Depends(svc)):
    await service.block_account(auth.account_id, account_id)
    return {"blocked": True}

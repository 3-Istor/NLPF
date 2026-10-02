"""Un seul contrat pricing : la BOM complète avec ses quatre montants actualisés."""
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ..price_data import MODEL_FILES

router = APIRouter(prefix='/api')


def _money(value: Decimal) -> float:
    # L'arrondi et le passage en nombre JSON appartiennent uniquement à ce
    # contrat de sortie ; le prix final a déjà été calculé en décimal complet.
    return float(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


@router.get('/prices', summary='BOM complète du modèle avec prix dynamiques')
def prices(request: Request, model: Annotated[str, Query(
    description='Motorisation : hybride, thermique ou electrique uniquement.',
    json_schema_extra={'enum': list(MODEL_FILES)},
)]):
    if model not in MODEL_FILES:
        raise HTTPException(
            status_code=400,
            detail='Unknown model. Allowed values: hybride, thermique, electrique',
        )
    service = getattr(request.app.state, 'price_simulation', None)
    if service is None:
        raise HTTPException(status_code=503, detail='Simulation pricing non initialisée.')
    return JSONResponse(jsonable_encoder(service.quote(model), custom_encoder={Decimal: _money}))

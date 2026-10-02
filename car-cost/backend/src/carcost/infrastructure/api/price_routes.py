"""Routes de simulation : montants transmis en chaînes, sans arrondi."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .errors import error_response


def require_price_simulation(request: Request) -> None:
    if getattr(request.app.state, 'price_simulation', None) is None:
        raise HTTPException(
            status_code=503,
            detail='Simulation indisponible : exporter CARCOST_PRICE_BOM puis redémarrer le serveur.',
        )


router = APIRouter(prefix='/api', dependencies=[Depends(require_price_simulation)])


def price_row(service, component, snapshot):
    price = service.price(component, snapshot)
    return {
        'id': component.id,
        'nom': component.name,
        'prix_unitaire_base_eur': str(component.base_price),
        'prix_unitaire_actuel_eur': str(price),
        'variation_pct': str((price / component.base_price - 1) * 100),
        'quantite': str(component.quantity),
        'cout_par_voiture_eur': str(price * component.quantity),
    }

@router.get('/prices')
def prices(request: Request):
    service = request.app.state.price_simulation
    snapshot = service.snapshot()
    return [price_row(service, part, snapshot) for part in service.components.values()]

@router.get('/prices/{component_id}')
def price(component_id: str, request: Request):
    service = request.app.state.price_simulation
    component = service.components.get(component_id)
    if component is None:
        return error_response(404, 'COMPONENT_NOT_FOUND', f'Composant inconnu : {component_id}')
    return price_row(service, component, service.snapshot())

@router.get('/vehicle-cost')
def vehicle_cost(request: Request):
    service = request.app.state.price_simulation
    snapshot = service.snapshot()
    total = service.vehicle_cost(snapshot)
    return {
        'date_simulee': snapshot.date.isoformat(),
        'cout_bom_eur': str(total),
        'variation_pct_depuis_debut': str((total / service.base_cost - 1) * 100),
    }

@router.get('/production-cost')
def production_cost(request: Request, vehicles: Annotated[int, Query(ge=0)] = 100):
    service = request.app.state.price_simulation
    snapshot = service.snapshot()
    production, stock, total = service.production_cost(vehicles, snapshot)
    return {
        'vehicles': vehicles,
        'cout_production_eur': str(production),
        'cout_stock_sav_eur': str(stock),
        'cout_total_eur': str(total),
        'date_simulee': snapshot.date.isoformat(),
    }

@router.get('/indices')
def indices(request: Request):
    snapshot = request.app.state.price_simulation.snapshot()
    return {'date_simulee': snapshot.date.isoformat(),
            'indices': {name: str(value) for name, value in snapshot.indices.items()}}

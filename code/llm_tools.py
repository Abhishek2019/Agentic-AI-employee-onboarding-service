from langchain.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import text


async def assign_seating_space(session_maker: async_sessionmaker[AsyncSession], seating_type=None) -> str:
    '''
    get the avaiulable seating space of required seating_type(seating_id) to an employee.
    
    '''
    async with session_maker() as session:
        async with session.begin():

            if not seating_type:
                seat_id = await session.execute(text("""
                        select (ss.seat_id, ss.seat_type) as available_seats from onboarding.seating_space ss
                        where ss.employee_id is null;

                    """)
                )
            else:
                seat_id = await session.execute(text(f"""
                        select (ss.seat_id, ss.seat_type) as available_seats from onboarding.seating_space ss
                        where ss.employee_id is null and ss.seat_type = {seating_type};

                    """)
                )
    if seat_id is None:
        return f"No available"
    return seat_id.all() 
    # return f"Assigned seat {seat_id} to employee."























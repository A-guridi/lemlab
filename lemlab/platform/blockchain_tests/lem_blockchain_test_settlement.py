import pytest
import pandas as pd
import time

from tqdm import tqdm

from lemlab.platform import lem, lem_settlement
from lemlab.platform.blockchain_tests import test_utils
from lemlab.platform.lem import _add_supplier_bids, clearing_da
from lemlab.bc_connection.bc_connection import BlockchainConnection

offers_blockchain_archive, bids_blockchain_archive = None, None
open_offers_blockchain, open_bids_blockchain = None, None
offers_db_archive, bids_db_archive = None, None
open_offers_db, open_bids_db = None, None
generate_bids_offer = True
user_infos_blockchain = None
user_infos_db = None
id_meters_blockchain = None
id_meters_db = None
config = None
quality_index = None
price_index = None
db_obj = None
bc_obj = None
verbose = True

verbose_bc = True
verbose_db = True
shuffle = False


# this method is executed before all the others, to get useful global variables, needed for the tests
@pytest.fixture(scope="session", autouse=True)
def setUp():
    global offers_blockchain_archive, bids_blockchain_archive, open_offers_blockchain, open_bids_blockchain, \
        offers_db_archive, bids_db_archive, open_offers_db, open_bids_db, user_infos_blockchain, user_infos_db, \
        id_meters_blockchain, id_meters_db, config, quality_energy, price_index, db_obj, bc_obj
    offers_blockchain_archive, bids_blockchain_archive, open_offers_blockchain, open_bids_blockchain, \
    offers_db_archive, bids_db_archive, open_offers_db, open_bids_db, user_infos_blockchain, user_infos_db, \
    id_meters_blockchain, id_meters_db, config, quality_energy, price_index, \
    db_obj, bc_obj = test_utils.setUp_test(generate_bids_offer)


# this test, tests that for every ts_delivery, a single clearing produces the same results on python and blockchain
def test_market_clearing_full():
    print("Starting full market clearing test")
    # Set clearing time
    t_clearing_start = round(time.time())

    start = time.time()
    market_results_python, _, _, _, market_results_blockchain = lem.market_clearing(db_obj=db_obj,
                                                                                    bc_obj=bc_obj,
                                                                                    config_lem=config['lem'],
                                                                                    t_override=t_clearing_start,
                                                                                    shuffle=shuffle,
                                                                                    verbose=verbose_db,
                                                                                    verbose_bc=verbose_bc,
                                                                                    bc_test=True)

    market_results_python = market_results_python['da']

    end = time.time()

    print("Market clearing done in", (end - start) / 60, "minutes")

    if shuffle:
        assert len(market_results_python) >= 0.1 * len(market_results_blockchain) or len(
            market_results_blockchain) >= 0.1 * len(market_results_python)
        try:
            pd.testing.assert_frame_equal(market_results_python, market_results_blockchain, check_dtype=False)
        except Exception as e:
            print(e)
    else:
        if market_results_blockchain.empty and market_results_python.empty:
            print("Both dataframes resulted empty")
            assert True
        else:
            pd.testing.assert_frame_equal(market_results_blockchain, market_results_python, check_dtype=False)
            assert True
    print("Market clearing full test passed and finished")


def test_balancing_energy():
    # this test requires first to have a fully completed market clearing stored in both the DB and the Blockchain
    print("Starting balancing energies test")
    # for the database
    list_ts_delivery = test_utils.test_simulate_meter_readings_from_market_results(db_obj=db_obj, rand_percent_var=15)
    lem_settlement.determine_balancing_energy(db_obj, list_ts_delivery)

    meter_readings_delta = db_obj.get_meter_readings_delta().sort_values(by=[db_obj.db_param.TS_DELIVERY, db_obj.db_param.ID_METER]).reset_index(drop=True)
    balancing_energies_db = db_obj.get_energy_balancing()

    assert not meter_readings_delta.empty, "Error: the delta meter readings are empty"
    assert not balancing_energies_db.empty, "Error: the balancing energy is empty"

    # for the blockchain
    # connect to our contract
    settlement_dict = config['db_connections']['bc_dict']
    settlement_dict["contract_name"] = "Settlement"
    bc_obj_set = BlockchainConnection(settlement_dict)
    # set the meter readings and determine balancing energy
    tx_hash = bc_obj_set.log_meter_readings_delta(meter_readings_delta)
    bc_obj_set.wait_for_transact(tx_hash)
    delta_meters = bc_obj_set.get_meter_readings_delta().sort_values(by=[db_obj.db_param.TS_DELIVERY, db_obj.db_param.ID_METER]).reset_index(drop=True)
    print("Deltas", delta_meters)
    market_results = bc_obj_set.get_market_results(return_list=True)
    print("MR", market_results)

    assert pd.testing.assert_frame_equal(delta_meters, meter_readings_delta), "Error, the delta meter dataframes " \
                                                                              "arent equal "

    balancing_energies_blockchain = bc_obj_set.determine_balancing_energy(list_ts_delivery)
    print("Bal energies", balancing_energies_blockchain)
    # asserts
    assert len(balancing_energies_db) == len(balancing_energies_blockchain), \
            "Error, the len of both dataframes isnt equal"
    if balancing_energies_db.empty and balancing_energies_blockchain.empty:
        print("Both dataframes are empty")
        assert False
    else:
        pd.testing.assert_frame_equal(balancing_energies_db, balancing_energies_blockchain)

    print("Balancing energies test finished")

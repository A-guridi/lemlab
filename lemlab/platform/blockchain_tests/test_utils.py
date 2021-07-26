import os
import time
import yaml
import pandas as pd

from lemlab.db_connection import db_connection, db_param
from lemlab.platform import lem
from lemlab.bc_connection.bc_connection import BlockchainConnection

from current_scenario_file import scenario_file_path


# this file initializes random data on the blockchain and on the database
def init_random_data():
    yaml_file = scenario_file_path
    # load configuration file
    with open(yaml_file) as config_file:
        config = yaml.load(config_file, Loader=yaml.FullLoader)
    # Create a db connection object
    db_obj = db_connection.DatabaseConnection(db_dict=config['db_connections']['database_connection_admin'],
                                              lem_config=config['lem'])
    # Initialize database
    db_obj.init_db(clear_tables=True, reformat_tables=True)

    # Create list of random user ids and meter ids
    ids_users_random = lem.create_user_ids(num=config['prosumer']['general_number_of'])
    ids_meter_random = lem.create_user_ids(num=config['prosumer']['general_number_of'])
    ids_market_agents = lem.create_user_ids(num=config['prosumer']['general_number_of'])

    bc_obj = BlockchainConnection(bc_dict=config['db_connections']['bc_dict'])  # connect to the platform contract
    bc_obj.clear_temp_data()
    bc_obj.clear_permanent_data()

    # Register meters and users on database
    for z in range(len(ids_users_random)):

        cols, types = db_obj.get_table_columns(db_obj.db_param.NAME_TABLE_INFO_USER, dtype=True)
        col_data = [ids_users_random[z], 1000, 0, 10000, 100, 'green', 10, 'zi', 0, ids_market_agents[z], 0, 0]
        if any([type(data) != typ for data, typ in zip(col_data, types)]):
            raise TypeError("The types of the data and the columns do not match for the info_user")
        df_insert = pd.DataFrame(
            data=[col_data],
            columns=cols)
        db_obj.register_user(df_in=df_insert)

        bc_obj.register_user(df_insert)

        cols, types = db_obj.get_table_columns(db_obj.db_param.NAME_TABLE_INFO_METER, dtype=True)
        col_data = [ids_meter_random[z], ids_users_random[z], "0", "virtual grid meter", 'aggregator', 'green', 0, 0,
                    'test']
        if any([type(data) != typ for data, typ in zip(col_data, types)]):
            raise TypeError("The types of data and columns do not match for the id_meter")
        df_insert = pd.DataFrame(
            data=[col_data],
            columns=cols)
        db_obj.register_meter(df_in=df_insert)

        tx_hash = bc_obj.register_meter(df_insert)

    bc_obj.wait_for_transact(tx_hash)

    if len(bc_obj.get_list_all_users()) == len(db_obj.get_list_all_users()) and len(
            bc_obj.get_list_main_meters()) == len(db_obj.get_list_main_meters()):
        print("Pre-setting: successfully stored " + str(len(db_obj.get_list_all_users())) + " users and " + str(
            len(db_obj.get_list_main_meters())) + " meters")
    else:
        print("Pre-setting: different number of user_infos and id_meters on blockchain and db")
        print("Pre-setting: user_infos on db: " + str(len(db_obj.get_list_all_users())))
        print("Pre-setting: user_infos on blockchain: " + str(len(bc_obj.get_list_all_users())))
        print("Pre-setting: id_meters on db: " + str(len(db_obj.get_list_main_meters())))
        print("Pre-setting: id_meters on blockchain: " + str(len(bc_obj.get_list_main_meters())))
        raise Exception("Error in inserting user_infos and id_meters")

    # Compute random market positions
    positions = lem.create_random_positions(db_obj=db_obj,
                                            config=config,
                                            ids_user=ids_users_random,
                                            n_positions=500,
                                            verbose=False)
    # Post positions to market
    db_obj.post_positions(positions)

    bids_db, offers_db = db_obj.get_open_positions()  # returns bids and offers from the database
    print(f"Pre-setting: a total of {len(bids_db) + len(offers_db)} market positions are pushed.")

    # for the blockchain, the quality of energy needs to be converted to int before storing it
    # however, before, in the DB the quality is stored as a string
    positions = lem._convert_qualities_to_int(db_obj, pd.concat([offers_db, bids_db]), config['lem']['types_quality'])

    temp = True  # if we wanna save the offers and bids as temporal data
    permt = False  # if we wanna save the offers and bids as permanent data

    tx_hash = bc_obj.push_all_positions(positions, temp, permt)
    bc_obj.wait_for_transact(tx_hash)

    if len(bc_obj.get_open_positions(isOffer=True, return_list=True)) == len(offers_db) and \
            len(bc_obj.get_open_positions(isOffer=False, return_list=True)) == len(bids_db):
        print(f"Pre-setting: stored {len(offers_db)} offers and {len(bids_db)} bids successfully.")
    else:
        print("Pre-setting: different number of offers and bids on blockchain and db")
        print("Pre-setting: offers on db: " + str(len(offers_db)))
        print(
            "Pre-setting: offers on blockchain: " + str(len(bc_obj.get_open_positions(isOffer=True, return_list=True))))
        print("Pre-setting: bids on db: " + str(len(bids_db)))
        print("Pre-setting: bids on blockchain: " + str(len(bc_obj.get_open_positions(isOffer=False, return_list=True))))


# I get basic variables from the blockchain. these variables are then used in the tests
def setUp_test(generate_bids_offer, timeout=600):
    yaml_file = scenario_file_path
    if generate_bids_offer:
        init_random_data()

    # load configuration file
    with open(f"" + yaml_file) as config_file:
        config = yaml.load(config_file, Loader=yaml.FullLoader)

    # Create a db connection object
    db_obj = db_connection.DatabaseConnection(db_dict=config['db_connections']['database_connection_admin'],
                                              lem_config=config['lem'])
    # Read offers and bids from db
    bids_db_archive, offers_db_archive = db_obj.get_positions_archive()
    open_bids_db, open_offers_db = db_obj.get_open_positions()
    user_infos_db, id_meters_db = [db_obj.get_info_user(user_id) for user_id in
                                   db_obj.get_list_all_users()], db_obj.get_info_meter()
    db_obj.end_connection()
    # print('Market archive contains', str(len(offers_db_archive)), 'valid offers and',
    #       str(len(bids_db_archive)), 'valid bids.')

    bc_obj = BlockchainConnection(bc_dict=config['db_connections']['bc_dict'])
    # blockchain_utils.setUpBlockchain(timeout=timeout)

    offers_blockchain_archive = bc_obj.get_open_positions(isOffer=True, temp=False, return_list=True)
    bids_blockchain_archive = bc_obj.get_open_positions(isOffer=False, temp=False, return_list=True)
    open_offers_blockchain = bc_obj.get_open_positions(isOffer=True, temp=True, return_list=True)
    open_bids_blockchain = bc_obj.get_open_positions(isOffer=False, temp=True, return_list=True)

    user_infos_blockchain = bc_obj.get_list_all_users(return_list=True)
    id_meters_blockchain = bc_obj.get_list_all_meters(return_list=True)

    return offers_blockchain_archive, bids_blockchain_archive, open_offers_blockchain, open_bids_blockchain, \
           offers_db_archive, bids_db_archive, open_offers_db, open_bids_db, user_infos_blockchain, user_infos_db, \
           id_meters_blockchain, id_meters_db, config, list(open_offers_db.keys()).index(db_param.QUALITY_ENERGY), \
           list(open_offers_db.keys()).index(db_param.PRICE_ENERGY), db_obj, bc_obj


def result_test(testname, passed):
    testname = str(testname)
    date = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    res = pd.DataFrame({"test_name": testname, "result": passed, "date": date}, index=[0])
    outfile = "test_results.xlsx"
    if os.path.isfile(outfile):
        f = pd.read_excel(outfile)
        f = pd.concat([f, res])
        with pd.ExcelWriter(outfile) as writer:
            f.to_excel(writer)
    else:
        with pd.ExcelWriter(outfile) as writer:
            res.to_excel(writer)


if __name__ == '__main__':
    init_random_data()

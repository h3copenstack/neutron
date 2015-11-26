#! /bin/bash
if [ "$1" == "" ] && [ "$2" == "" ]; then
    echo "Usage: ./setup.sh <MYSQL_ROOT_PASSWORD> <PYTHON_VERSION>."
    echo "PYTHON_VERSION: # python --version"
    echo "                # Python 2.7.x"
    echo "./setup.sh **** 2.7"
    exit 1
fi

BASE_DIR="/usr/lib/python$2/dist-packages/"
sql_root='root'
sql_password=$1
DEST_DIR="${BASE_DIR}/neutron/plugins/ml2/drivers/"

echo "Starting setup HP ml2 driver." 

echo "Create table for HP driver. "
create_table_nets='use neutron; CREATE TABLE hp_related_nets(tenant_id varchar(255) default null, id varchar(36) not null primary key, network_id varchar(36) default null, segmentation_id int(11) default NULL, segmentation_type varchar(12) default NULL);'
create_table_vms='use neutron; CREATE TABLE hp_related_vms(tenant_id varchar(255) default null, id varchar(36) not null primary key, device_id varchar(255) default NULL, host_id varchar(255) default null, port_id varchar(36) default null, network_id varchar(36) default null);'
mysql -u${sql_root} -p${sql_password} -e "${create_table_nets}"
mysql -u${sql_root} -p${sql_password} -e "${create_table_vms}"

echo "Copy HP driver source code to ${DEST_DIR}"
cp -ar hp ${DEST_DIR}
chmod +x ${DEST_DIR}/hp/*

ETC="/etc/neutron/plugins/ml2/"
echo "Create ml2_conf_hp.ini in $ETC"
cp ./etc/neutron/plugins/ml2/ml2_conf_hp.ini $ETC

echo "Modify egg-files."
egg_dir=$(find ${BASE_DIR}  -type d | grep "neutron-.*egg-info")
entry_file=${egg_dir}/entry_points.txt
entry="hp = neutron.plugins.ml2.drivers.hp.mechanism_hp:HPDriver"
sed -i "/neutron.ml2.mechanism_drivers/a ${entry}" ${entry_file}

echo "Finish."

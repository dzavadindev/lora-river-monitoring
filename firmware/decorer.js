function decodeUplink(input) {
  const bytes = input.bytes;

  const temp  = (bytes[2] << 24) >> 24; // buffer has temp as u8, interpret as signed i8
  const level = bytes[1];
  const flow  = bytes[0];

  const ascii = String.fromCharCode(...bytes.slice(3)); // everything after third byte
  const [latStr, lonStr] = ascii.split(','); // to get lat and long 

  const lat = parseFloat(latStr);
  const lon = parseFloat(lonStr);

  return {
    data: {
      flow_deg: flow,
      water_level_mm: level,
      water_temp_c: temp,
      latitude: lat,
      longitude: lon
    }
  };
}

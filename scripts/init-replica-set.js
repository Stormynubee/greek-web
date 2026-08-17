try {
  rs.status();
  print("MongoDB replica set is already initialized.");
} catch (error) {
  rs.initiate({
    _id: "rs0",
    members: [{ _id: 0, host: "localhost:27017" }],
  });
  print("MongoDB replica set initialized.");
}
